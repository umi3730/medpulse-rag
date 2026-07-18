#!/usr/bin/env python3
# coding: utf-8
"""Local Qdrant vector store for GraphRAG memory and retrieval snippets."""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .memory_store import DEFAULT_SESSION_ID, DEFAULT_USER_ID
from .embedding_provider import (
    EmbeddingProvider,
    HashEmbeddingProvider,
    create_embedding_provider,
)


DEFAULT_QDRANT_PATH = Path(__file__).resolve().parent.parent / "data" / "qdrant"
DEFAULT_COLLECTION = "medical_graphrag_memory"
VECTOR_SIZE = 384
DEFAULT_SCORE_THRESHOLD = 0.30


class QdrantVectorStore:
    """Embedded Qdrant store backed by a pluggable embedding provider."""

    def __init__(
        self,
        path: str | Path = DEFAULT_QDRANT_PATH,
        collection_name: str | None = None,
        vector_size: int | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError as exc:
            raise ImportError("qdrant-client is not installed") from exc

        self.embedding_fallback_reason = ""
        if embedding_provider is not None:
            self.embedding_provider = embedding_provider
        elif vector_size is not None:
            self.embedding_provider = HashEmbeddingProvider(vector_size)
        else:
            try:
                self.embedding_provider = create_embedding_provider(fallback_to_hash=False)
            except Exception as exc:
                self.embedding_provider = HashEmbeddingProvider()
                self.embedding_fallback_reason = str(exc)

        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.vector_size = self.embedding_provider.dimension
        self.collection_name = collection_name or self._provider_collection_name()
        self.client = QdrantClient(path=str(self.path))
        self._models = __import__("qdrant_client.models", fromlist=["models"])

        existing = {c.name for c in self.client.get_collections().collections}
        if self.collection_name not in existing:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
            )

    def add_text(
        self,
        *,
        text: str,
        payload: dict[str, Any] | None = None,
        point_id: str | None = None,
    ) -> str:
        clean_text = text.strip()
        if not clean_text:
            return ""

        models = self._models
        point_id = point_id or str(uuid.uuid4())
        payload_data = {"text": clean_text, **(payload or {})}
        self.client.upsert(
            collection_name=self.collection_name,
            points=[
                models.PointStruct(
                    id=point_id,
                    vector=self.embedding_provider.embed_document(clean_text),
                    payload=payload_data,
                )
            ],
        )
        return point_id

    def add_memory_turn(
        self,
        *,
        question: str,
        answer: str,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
        entities: dict[str, list[str]] | None = None,
        intents: list[str] | None = None,
        quality_status: str = "unverified",
    ) -> str:
        entity_text = self._format_entities(entities or {})
        text = f"用户问题：{question}"
        if entity_text:
            text += f"\n相关实体：{entity_text}"
        return self.add_text(
            text=text,
            payload={
                "kind": "memory_turn",
                "memory_kind": "conversation",
                "quality_status": quality_status,
                "evidence_eligible": False,
                "schema_version": 2,
                "embedding_provider": self.embedding_provider.name,
                "embedding_model": self.embedding_provider.model_name,
                "embedding_dimension": self.embedding_provider.dimension,
                "user_id": user_id,
                "session_id": session_id,
                "question": question,
                "answer": answer[:1000],
                "entities": entities or {},
                "intents": intents or [],
            },
        )

    def search(
        self,
        query: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 5,
        min_score: float | None = DEFAULT_SCORE_THRESHOLD,
        memory_kind: str | None = "conversation",
    ) -> list[dict[str, Any]]:
        if not query.strip():
            return []

        models = self._models
        query_filter = None
        conditions = []
        if user_id:
            conditions.append(
                models.FieldCondition(
                    key="user_id",
                    match=models.MatchValue(value=user_id),
                )
            )
        if session_id:
            conditions.append(
                models.FieldCondition(
                    key="session_id",
                    match=models.MatchValue(value=session_id),
                )
            )
        if memory_kind:
            conditions.append(
                models.FieldCondition(
                    key="memory_kind",
                    match=models.MatchValue(value=memory_kind),
                )
            )
        if conditions:
            query_filter = models.Filter(
                must=conditions,
            )

        response = self.client.query_points(
            collection_name=self.collection_name,
            query=self.embedding_provider.embed_query(query),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        rows = response.points
        hits = [
            {
                "id": str(row.id),
                "score": float(row.score),
                "payload": dict(row.payload or {}),
            }
            for row in rows
        ]
        if min_score is not None:
            hits = [hit for hit in hits if hit["score"] >= min_score]
        return hits

    def build_context(
        self,
        query: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        limit: int = 3,
        min_score: float | None = DEFAULT_SCORE_THRESHOLD,
    ) -> dict[str, Any]:
        hits = self.search(
            query,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            min_score=min_score,
            memory_kind="conversation",
        )
        parts = []
        for idx, hit in enumerate(hits, start=1):
            payload = hit["payload"]
            question = str(payload.get("question", "")).strip()
            entities = self._format_entities(payload.get("entities") or {})
            if question:
                item = f"[Conversation Recall {idx} | score={hit['score']:.3f}]\n用户曾问：{question[:300]}"
                if entities:
                    item += f"\n涉及实体：{entities}"
                parts.append(item)
        return {
            "context_text": "\n\n".join(parts),
            "memory_scope": "conversation_only",
            "hits": hits,
        }

    def clear(
        self,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        if user_id or session_id:
            models = self._models
            conditions = []
            if user_id:
                conditions.append(
                    models.FieldCondition(
                        key="user_id",
                        match=models.MatchValue(value=user_id),
                    )
                )
            if session_id:
                conditions.append(
                    models.FieldCondition(
                        key="session_id",
                        match=models.MatchValue(value=session_id),
                    )
                )
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=models.FilterSelector(
                    filter=models.Filter(must=conditions),
                ),
                wait=True,
            )
            return {
                "collection": self.collection_name,
                "cleared": True,
                "user_id": user_id,
                "session_id": session_id,
            }

        self.client.delete_collection(collection_name=self.collection_name)
        from qdrant_client.models import Distance, VectorParams

        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )
        return {"collection": self.collection_name, "cleared": True}

    def stats(self) -> dict[str, Any]:
        info = self.client.get_collection(collection_name=self.collection_name)
        return {
            "collection": self.collection_name,
            "path": str(self.path),
            "points_count": getattr(info, "points_count", 0) or 0,
            "vectors_count": getattr(info, "vectors_count", None),
            "embedding_provider": self.embedding_provider.name,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimension": self.embedding_provider.dimension,
            "embedding_fallback_reason": self.embedding_fallback_reason,
        }

    def close(self) -> None:
        self.client.close()

    def embed(self, text: str) -> list[float]:
        return self.embedding_provider.embed_document(text)

    def _provider_collection_name(self) -> str:
        identity = (
            f"{self.embedding_provider.name}_"
            f"{self.embedding_provider.model_name}_"
            f"{self.embedding_provider.dimension}"
        )
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", identity).strip("_").lower()
        return f"{DEFAULT_COLLECTION}__{safe}"[:255]

    @staticmethod
    def _format_entities(entities: dict[str, list[str]]) -> str:
        return "；".join(
            f"{entity_type}: {'、'.join(names)}"
            for entity_type, names in entities.items()
            if names
        )
