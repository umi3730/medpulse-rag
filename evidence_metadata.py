"""Shared evidence metadata defaults for ingestion and GraphRAG retrieval."""
from __future__ import annotations

from typing import Any


DEFAULT_SOURCE_NAME = "寻医问药网历史数据集"
DEFAULT_SOURCE_URL = ""
DEFAULT_UPDATED_AT = "unknown"
DEFAULT_EVIDENCE_LEVEL = "legacy_unverified"


def normalize_evidence_metadata(data: dict[str, Any] | None = None) -> dict[str, str]:
    raw = data or {}
    return {
        "source_name": str(raw.get("source_name") or DEFAULT_SOURCE_NAME),
        "source_url": str(raw.get("source_url") or DEFAULT_SOURCE_URL),
        "updated_at": str(raw.get("updated_at") or DEFAULT_UPDATED_AT),
        "evidence_level": str(raw.get("evidence_level") or DEFAULT_EVIDENCE_LEVEL),
    }
