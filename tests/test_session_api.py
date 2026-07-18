from __future__ import annotations

import unittest

import server.app as app_module
from server.models import SessionRenameRequest


class FakeMemoryStore:
    def __init__(self):
        self.renamed = None
        self.deleted = None

    def list_sessions(self, **kwargs):
        return {"sessions": [], "total": 0, "limit": kwargs["limit"], "offset": kwargs["offset"], "has_more": False}

    def rename_session(self, **kwargs):
        self.renamed = kwargs
        return kwargs["session_id"] == "owned_session"

    def delete_session(self, **kwargs):
        self.deleted = kwargs
        return {"sessions_deleted": 1, "turns_deleted": 2, "entities_deleted": 1}


class FakeVectorStore:
    def __init__(self):
        self.cleared = None

    def clear(self, **kwargs):
        self.cleared = kwargs
        return {"cleared": True}


class FakeBot:
    def __init__(self):
        self.memory_store = FakeMemoryStore()
        self.vector_store = FakeVectorStore()


class SessionApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.original = app_module._graphrag_bot
        self.bot = FakeBot()
        app_module._graphrag_bot = self.bot

    async def asyncTearDown(self) -> None:
        app_module._graphrag_bot = self.original

    async def test_list_forwards_search_and_pagination(self) -> None:
        result = await app_module.graphrag_sessions(
            user_id="user_a", limit=10, offset=20, q="高血压",
        )
        self.assertEqual(result["offset"], 20)
        self.assertEqual(result["total"], 0)

    async def test_rename_is_user_scoped(self) -> None:
        result = await app_module.rename_graphrag_session(
            "owned_session", SessionRenameRequest(user_id="user_a", title=" 血压  管理 "),
        )
        self.assertTrue(result["updated"])
        self.assertEqual(result["title"], "血压 管理")
        self.assertEqual(self.bot.memory_store.renamed["user_id"], "user_a")

    async def test_delete_clears_vector_and_sqlite_with_same_identity(self) -> None:
        result = await app_module.delete_graphrag_session(
            "owned_session", user_id="user_a",
        )
        identity = {"user_id": "user_a", "session_id": "owned_session"}
        self.assertEqual(self.bot.vector_store.cleared, identity)
        self.assertEqual(self.bot.memory_store.deleted, identity)
        self.assertTrue(result["vector"]["cleared"])
        self.assertEqual(result["turns_deleted"], 2)


if __name__ == "__main__":
    unittest.main()
