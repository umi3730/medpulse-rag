"""Pluggable embedding providers for Qdrant-backed conversation recall."""
from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from pathlib import Path

from settings import (
    EMBEDDING_CACHE_DIR,
    EMBEDDING_DEVICE,
    EMBEDDING_LOCAL_FILES_ONLY,
    EMBEDDING_MODEL,
    EMBEDDING_PROVIDER,
    EMBEDDING_QUERY_PREFIX,
)


class EmbeddingProvider(ABC):
    name: str
    model_name: str
    dimension: int

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_document(self, text: str) -> list[float]: ...

    @property
    def collection_suffix(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", self.model_name.lower()).strip("-")
        return f"{self.name}-{slug}-{self.dimension}-v2"


class HashEmbeddingProvider(EmbeddingProvider):
    name = "hash"
    model_name = "blake2b-token-hash"

    def __init__(self, dimension: int = 384):
        self.dimension = dimension

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def embed_document(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        tokens = self._tokens(text) or [text]
        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dimension
            vector[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    @staticmethod
    def _tokens(text: str) -> list[str]:
        normalized = text.lower()
        latin = re.findall(r"[a-z0-9_]+", normalized)
        chinese = re.findall(r"[\u4e00-\u9fff]", normalized)
        bigrams = [normalized[i:i + 2] for i in range(max(len(normalized) - 1, 0))]
        return latin + chinese + bigrams[:512]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    name = "sentence-transformers"

    def __init__(
        self,
        model_name: str = EMBEDDING_MODEL,
        cache_dir: str | Path = EMBEDDING_CACHE_DIR,
        device: str = EMBEDDING_DEVICE,
        local_files_only: bool = EMBEDDING_LOCAL_FILES_ONLY,
        query_prefix: str = EMBEDDING_QUERY_PREFIX,
    ):
        from sentence_transformers import SentenceTransformer

        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.query_prefix = query_prefix
        self.model = SentenceTransformer(
            model_name,
            cache_folder=str(self.cache_dir),
            device=device,
            local_files_only=local_files_only,
        )
        dimension_getter = getattr(
            self.model,
            "get_embedding_dimension",
            self.model.get_sentence_embedding_dimension,
        )
        dimension = dimension_getter()
        if not dimension:
            raise ValueError(f"Cannot determine embedding dimension for {model_name}")
        self.dimension = int(dimension)

    def embed_query(self, text: str) -> list[float]:
        return self.model.encode(
            f"{self.query_prefix}{text}",
            normalize_embeddings=True,
            convert_to_numpy=True,
        ).tolist()

    def embed_document(self, text: str) -> list[float]:
        encoder = getattr(self.model, "encode_document", self.model.encode)
        return encoder(text, normalize_embeddings=True, convert_to_numpy=True).tolist()


def create_embedding_provider(
    provider_name: str = EMBEDDING_PROVIDER,
    model_name: str = EMBEDDING_MODEL,
    cache_dir: str | Path = EMBEDDING_CACHE_DIR,
    *,
    fallback_to_hash: bool = True,
) -> EmbeddingProvider:
    try:
        normalized = provider_name.strip().lower().replace("-", "_")
        if normalized in {"sentence_transformers", "sentence_transformer", "bge"}:
            return SentenceTransformerEmbeddingProvider(model_name=model_name, cache_dir=cache_dir)
        if normalized == "hash":
            return HashEmbeddingProvider()
        raise ValueError(f"Unsupported embedding provider: {provider_name}")
    except Exception:
        if fallback_to_hash:
            return HashEmbeddingProvider()
        raise
