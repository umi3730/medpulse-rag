#!/usr/bin/env python3
# coding: utf-8
"""SQLite-backed conversation memory for GraphRAG."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_USER_ID = "anonymous"
DEFAULT_SESSION_ID = "default"
DEFAULT_DB_PATH = Path(os.environ.get(
    "MEMORY_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "memory.sqlite3"),
))


class SQLiteMemoryStore:
    """Small local memory store for recent turns and mentioned entities."""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_turns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'anonymous',
                    session_id TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    intents_json TEXT NOT NULL DEFAULT '[]',
                    entities_json TEXT NOT NULL DEFAULT '{}',
                    memory_kind TEXT NOT NULL DEFAULT 'conversation',
                    quality_status TEXT NOT NULL DEFAULT 'unverified',
                    evidence_eligible INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'anonymous',
                    session_id TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    entity_name TEXT NOT NULL,
                    mention_count INTEGER NOT NULL DEFAULT 1,
                    last_seen_at TEXT NOT NULL,
                    UNIQUE(user_id, session_id, entity_type, entity_name)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, session_id)
                )
                """
            )
            self._ensure_column(conn, "memory_turns", "user_id", "TEXT NOT NULL DEFAULT 'anonymous'")
            self._ensure_column(conn, "memory_turns", "memory_kind", "TEXT NOT NULL DEFAULT 'conversation'")
            self._ensure_column(conn, "memory_turns", "quality_status", "TEXT NOT NULL DEFAULT 'unverified'")
            self._ensure_column(conn, "memory_turns", "evidence_eligible", "INTEGER NOT NULL DEFAULT 0")
            self._ensure_column(conn, "memory_entities", "user_id", "TEXT NOT NULL DEFAULT 'anonymous'")
            self._ensure_entity_identity_key(conn)
            conn.execute(
                """
                INSERT OR IGNORE INTO chat_sessions
                    (user_id, session_id, title, created_at, updated_at)
                SELECT user_id, session_id, '', MIN(created_at), MAX(created_at)
                FROM memory_turns
                GROUP BY user_id, session_id
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_turns_user_session_created "
                "ON memory_turns(user_id, session_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_memory_entities_user_session_seen "
                "ON memory_entities(user_id, session_id, last_seen_at)"
            )

    @staticmethod
    def _ensure_column(
        conn: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    @staticmethod
    def _ensure_entity_identity_key(conn: sqlite3.Connection) -> None:
        expected = ["user_id", "session_id", "entity_type", "entity_name"]
        for index_row in conn.execute("PRAGMA index_list(memory_entities)").fetchall():
            if not index_row[2]:
                continue
            columns = [
                info_row[2]
                for info_row in conn.execute(f"PRAGMA index_info({index_row[1]})").fetchall()
            ]
            if columns == expected:
                return

        conn.execute("DROP TABLE IF EXISTS memory_entities_identity_migration")
        conn.execute(
            """
            CREATE TABLE memory_entities_identity_migration (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL DEFAULT 'anonymous',
                session_id TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                mention_count INTEGER NOT NULL DEFAULT 1,
                last_seen_at TEXT NOT NULL,
                UNIQUE(user_id, session_id, entity_type, entity_name)
            )
            """
        )
        conn.execute(
            """
            INSERT OR REPLACE INTO memory_entities_identity_migration
                (id, user_id, session_id, entity_type, entity_name, mention_count, last_seen_at)
            SELECT id, user_id, session_id, entity_type, entity_name, mention_count, last_seen_at
            FROM memory_entities
            """
        )
        conn.execute("DROP TABLE memory_entities")
        conn.execute("ALTER TABLE memory_entities_identity_migration RENAME TO memory_entities")

    def add_turn(
        self,
        *,
        question: str,
        answer: str,
        intents: list[str] | None = None,
        entities: dict[str, list[str]] | None = None,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
        memory_kind: str = "conversation",
        quality_status: str = "unverified",
        evidence_eligible: bool = False,
    ) -> None:
        now = self._now()
        clean_entities = self._clean_entities(entities or {})
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (user_id, session_id, title, created_at, updated_at)
                VALUES (?, ?, '', ?, ?)
                ON CONFLICT(user_id, session_id)
                DO UPDATE SET updated_at = excluded.updated_at
                """,
                (user_id, session_id, now, now),
            )
            conn.execute(
                """
                INSERT INTO memory_turns
                    (user_id, session_id, question, answer, intents_json, entities_json,
                     memory_kind, quality_status, evidence_eligible, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    session_id,
                    question,
                    answer,
                    json.dumps(intents or [], ensure_ascii=False),
                    json.dumps(clean_entities, ensure_ascii=False),
                    memory_kind,
                    quality_status,
                    int(evidence_eligible),
                    now,
                ),
            )
            for entity_type, names in clean_entities.items():
                for name in names:
                    conn.execute(
                        """
                        INSERT INTO memory_entities
                            (user_id, session_id, entity_type, entity_name, mention_count, last_seen_at)
                        VALUES (?, ?, ?, ?, 1, ?)
                        ON CONFLICT(user_id, session_id, entity_type, entity_name)
                        DO UPDATE SET
                            mention_count = mention_count + 1,
                            last_seen_at = excluded.last_seen_at
                        """,
                        (user_id, session_id, entity_type, name, now),
                    )

    def get_recent_turns(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
        limit: int = 6,
    ) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT question, answer, intents_json, entities_json,
                       memory_kind, quality_status, evidence_eligible, created_at
                FROM memory_turns
                WHERE user_id = ? AND session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (user_id, session_id, limit),
            ).fetchall()
        turns = []
        for row in reversed(rows):
            turns.append(
                {
                    "question": row["question"],
                    "answer": row["answer"],
                    "intents": self._loads(row["intents_json"], []),
                    "entities": self._loads(row["entities_json"], {}),
                    "memory_kind": row["memory_kind"],
                    "quality_status": row["quality_status"],
                    "evidence_eligible": bool(row["evidence_eligible"]),
                    "created_at": row["created_at"],
                }
            )
        return turns

    def list_sessions(
        self,
        user_id: str = DEFAULT_USER_ID,
        limit: int = 30,
        offset: int = 0,
        query: str = "",
    ) -> dict[str, Any]:
        clean_query = query.strip()
        escaped_query = clean_query.replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped_query}%"
        with self._lock, self._connect() as conn:
            total = conn.execute(
                """
                SELECT COUNT(*)
                FROM chat_sessions AS sessions
                WHERE sessions.user_id = ?
                  AND (? = '' OR sessions.title LIKE ? ESCAPE '\\' OR EXISTS (
                      SELECT 1 FROM memory_turns AS turns
                      WHERE turns.user_id = sessions.user_id
                        AND turns.session_id = sessions.session_id
                        AND (turns.question LIKE ? ESCAPE '\\' OR turns.answer LIKE ? ESCAPE '\\')
                  ))
                """,
                (user_id, clean_query, pattern, pattern, pattern),
            ).fetchone()[0]
            rows = conn.execute(
                """
                WITH session_summary AS (
                    SELECT
                        session_id,
                        MIN(id) AS first_turn_id,
                        MAX(id) AS last_turn_id,
                        COUNT(*) AS turn_count,
                        MIN(created_at) AS created_at,
                        MAX(created_at) AS updated_at
                    FROM memory_turns
                    WHERE user_id = ?
                    GROUP BY session_id
                )
                SELECT
                    summary.session_id,
                    summary.turn_count,
                    summary.created_at,
                    summary.updated_at,
                    CASE WHEN sessions.title <> '' THEN sessions.title ELSE first_turn.question END AS title,
                    sessions.title <> '' AS is_custom_title,
                    last_turn.question AS last_question
                FROM session_summary AS summary
                JOIN chat_sessions AS sessions
                  ON sessions.user_id = ? AND sessions.session_id = summary.session_id
                JOIN memory_turns AS first_turn ON first_turn.id = summary.first_turn_id
                JOIN memory_turns AS last_turn ON last_turn.id = summary.last_turn_id
                WHERE (? = '' OR sessions.title LIKE ? ESCAPE '\\'
                    OR first_turn.question LIKE ? ESCAPE '\\'
                    OR last_turn.question LIKE ? ESCAPE '\\'
                    OR EXISTS (
                        SELECT 1 FROM memory_turns AS searched
                        WHERE searched.user_id = ?
                          AND searched.session_id = summary.session_id
                          AND (searched.question LIKE ? ESCAPE '\\' OR searched.answer LIKE ? ESCAPE '\\')
                    ))
                ORDER BY summary.last_turn_id DESC
                LIMIT ? OFFSET ?
                """,
                (
                    user_id, user_id, clean_query, pattern, pattern, pattern,
                    user_id, pattern, pattern, limit, offset,
                ),
            ).fetchall()
        return {
            "sessions": [dict(row) for row in rows],
            "total": int(total),
            "limit": limit,
            "offset": offset,
            "has_more": offset + len(rows) < total,
        }

    def rename_session(self, *, user_id: str, session_id: str, title: str) -> bool:
        clean_title = " ".join(title.split()).strip()[:80]
        if not clean_title:
            raise ValueError("session title cannot be empty")
        with self._lock, self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE chat_sessions SET title = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ?
                """,
                (clean_title, self._now(), user_id, session_id),
            ).rowcount
        return bool(updated)

    def delete_session(self, *, user_id: str, session_id: str) -> dict[str, int]:
        with self._lock, self._connect() as conn:
            turn_count = conn.execute(
                "DELETE FROM memory_turns WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).rowcount
            entity_count = conn.execute(
                "DELETE FROM memory_entities WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).rowcount
            session_count = conn.execute(
                "DELETE FROM chat_sessions WHERE user_id = ? AND session_id = ?",
                (user_id, session_id),
            ).rowcount
        return {
            "sessions_deleted": session_count,
            "turns_deleted": turn_count,
            "entities_deleted": entity_count,
        }

    def get_session_turns(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT question, answer, intents_json, entities_json,
                       memory_kind, quality_status, evidence_eligible, created_at
                FROM memory_turns
                WHERE user_id = ? AND session_id = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (user_id, session_id, limit),
            ).fetchall()
        return [
            {
                "question": row["question"],
                "answer": row["answer"],
                "intents": self._loads(row["intents_json"], []),
                "entities": self._loads(row["entities_json"], {}),
                "memory_kind": row["memory_kind"],
                "quality_status": row["quality_status"],
                "evidence_eligible": bool(row["evidence_eligible"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def get_known_entities(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
        limit: int = 12,
    ) -> dict[str, list[str]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT entity_type, entity_name
                FROM memory_entities
                WHERE user_id = ? AND session_id = ?
                ORDER BY last_seen_at DESC, mention_count DESC
                LIMIT ?
                """,
                (user_id, session_id, limit),
            ).fetchall()
        entities: dict[str, list[str]] = {}
        for row in rows:
            entities.setdefault(row["entity_type"], [])
            if row["entity_name"] not in entities[row["entity_type"]]:
                entities[row["entity_type"]].append(row["entity_name"])
        return entities

    def build_context(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> dict[str, Any]:
        turns = self.get_recent_turns(user_id=user_id, session_id=session_id)
        entities = self.get_known_entities(user_id=user_id, session_id=session_id)
        parts: list[str] = []
        if entities:
            entity_text = "；".join(
                f"{entity_type}: {'、'.join(names)}"
                for entity_type, names in entities.items()
                if names
            )
            if entity_text:
                parts.append(f"已知历史实体：{entity_text}")
        if turns:
            parts.append("最近用户问题（仅用于理解上下文，不是医学证据）：")
            for turn in turns[-3:]:
                parts.append(f"- {turn['question']}")

        return {
            "context_text": "\n".join(parts),
            "memory_scope": "conversation_only",
            "recent_turns": turns,
            "entities": entities,
        }

    def clear(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> dict[str, int]:
        return self.delete_session(user_id=user_id, session_id=session_id)

    def snapshot(
        self,
        user_id: str = DEFAULT_USER_ID,
        session_id: str = DEFAULT_SESSION_ID,
    ) -> dict[str, Any]:
        return {
            "user_id": user_id,
            "session_id": session_id,
            "recent_turns": self.get_recent_turns(user_id=user_id, session_id=session_id),
            "entities": self.get_known_entities(user_id=user_id, session_id=session_id),
        }

    @staticmethod
    def _clean_entities(entities: dict[str, list[str]]) -> dict[str, list[str]]:
        cleaned: dict[str, list[str]] = {}
        for entity_type, names in entities.items():
            for name in names or []:
                value = str(name).strip()
                if not value:
                    continue
                cleaned.setdefault(entity_type, [])
                if value not in cleaned[entity_type]:
                    cleaned[entity_type].append(value)
        return cleaned

    @staticmethod
    def _loads(raw: str, default: Any) -> Any:
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
