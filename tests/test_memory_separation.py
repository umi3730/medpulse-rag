from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from graphrag.memory_store import SQLiteMemoryStore
from graphrag.embedding_provider import HashEmbeddingProvider
from graphrag.vector_store import QdrantVectorStore


class SQLiteMemorySeparationTests(unittest.TestCase):
    def test_session_management_is_paginated_searchable_and_user_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteMemoryStore(Path(tmpdir) / "memory.sqlite3")
            for session_id, question in (("session_a", "高血压如何预防？"), ("session_b", "糖尿病检查什么？")):
                store.add_turn(
                    question=question, answer="回答", user_id="user_a", session_id=session_id,
                )
            store.add_turn(
                question="另一个用户的问题", answer="回答", user_id="user_b", session_id="session_a",
            )

            self.assertTrue(store.rename_session(
                user_id="user_a", session_id="session_a", title="血压管理",
            ))
            self.assertFalse(store.rename_session(
                user_id="user_b", session_id="session_b", title="越权标题",
            ))
            first_page = store.list_sessions(user_id="user_a", limit=1, offset=0)
            self.assertEqual(first_page["total"], 2)
            self.assertTrue(first_page["has_more"])
            search = store.list_sessions(user_id="user_a", query="血压")
            self.assertEqual(search["total"], 1)
            self.assertEqual(search["sessions"][0]["title"], "血压管理")

            deleted = store.delete_session(user_id="user_a", session_id="session_a")
            self.assertEqual(deleted["sessions_deleted"], 1)
            self.assertEqual(store.get_session_turns(user_id="user_a", session_id="session_a"), [])
            self.assertEqual(len(store.get_session_turns(user_id="user_b", session_id="session_a")), 1)

    def test_assistant_answer_is_not_in_model_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SQLiteMemoryStore(Path(tmpdir) / "memory.sqlite3")
            store.add_turn(
                question="高血压是什么？",
                answer="WRONG_MEDICAL_CLAIM",
                entities={"disease": ["高血压"]},
                user_id="user_a",
                session_id="session_a",
            )
            context = store.build_context(user_id="user_a", session_id="session_a")
            history = store.get_session_turns(user_id="user_a", session_id="session_a")
            self.assertNotIn("WRONG_MEDICAL_CLAIM", context["context_text"])
            self.assertIn("高血压是什么", context["context_text"])
            self.assertEqual(history[0]["answer"], "WRONG_MEDICAL_CLAIM")
            self.assertEqual(history[0]["memory_kind"], "conversation")
            self.assertFalse(history[0]["evidence_eligible"])

    def test_old_sqlite_schema_is_migrated_with_safe_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy.sqlite3"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE memory_turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id TEXT NOT NULL DEFAULT 'anonymous',
                        session_id TEXT NOT NULL,
                        question TEXT NOT NULL,
                        answer TEXT NOT NULL,
                        intents_json TEXT NOT NULL DEFAULT '[]',
                        entities_json TEXT NOT NULL DEFAULT '{}',
                        created_at TEXT NOT NULL
                    )
                    """
                )
            store = SQLiteMemoryStore(db_path)
            conn = store._connect()
            try:
                columns = {
                    row[1] for row in conn.execute("PRAGMA table_info(memory_turns)").fetchall()
                }
            finally:
                conn.close()
            self.assertTrue({
                "memory_kind", "quality_status", "evidence_eligible"
            }.issubset(columns))


class QdrantMemorySeparationTests(unittest.TestCase):
    def test_session_delete_does_not_remove_same_session_id_for_another_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                store = QdrantVectorStore(
                    Path(tmpdir) / "qdrant",
                    embedding_provider=HashEmbeddingProvider(),
                )
            except ImportError:
                self.skipTest("qdrant-client is not installed")
            try:
                for user_id in ("user_a", "user_b"):
                    store.add_memory_turn(
                        question=f"{user_id} 的问题", answer="回答",
                        user_id=user_id, session_id="shared_session",
                    )
                store.clear(user_id="user_a", session_id="shared_session")
                self.assertEqual(store.search(
                    "问题", user_id="user_a", session_id="shared_session", min_score=None,
                ), [])
                self.assertEqual(len(store.search(
                    "问题", user_id="user_b", session_id="shared_session", min_score=None,
                )), 1)
            finally:
                store.close()

    def test_legacy_vectors_are_quarantined_and_answers_are_not_rendered(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                store = QdrantVectorStore(
                    Path(tmpdir) / "qdrant",
                    embedding_provider=HashEmbeddingProvider(),
                )
            except ImportError:
                self.skipTest("qdrant-client is not installed")
            try:
                store.add_memory_turn(
                    question="高血压是什么？",
                    answer="WRONG_VECTOR_ANSWER",
                    entities={"disease": ["高血压"]},
                    user_id="user_a",
                    session_id="session_a",
                )
                store.add_text(
                    text="高血压旧回答",
                    payload={
                        "user_id": "user_a",
                        "session_id": "session_a",
                        "answer": "LEGACY_WRONG_ANSWER",
                    },
                )
                hits = store.search(
                    "高血压",
                    user_id="user_a",
                    session_id="session_a",
                    min_score=None,
                )
                context = store.build_context(
                    "高血压",
                    user_id="user_a",
                    session_id="session_a",
                    min_score=None,
                )
                self.assertEqual(len(hits), 1)
                self.assertEqual(hits[0]["payload"]["memory_kind"], "conversation")
                self.assertNotIn("WRONG_VECTOR_ANSWER", context["context_text"])
                self.assertNotIn("LEGACY_WRONG_ANSWER", context["context_text"])
                self.assertIn("高血压是什么", context["context_text"])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
