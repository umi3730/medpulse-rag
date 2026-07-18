"""Load and validate curated medical evidence JSONL files."""
from __future__ import annotations

import json
from pathlib import Path

from evidence_schema import EvidenceRecord


def load_evidence_records(path: str | Path) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    seen: set[str] = set()
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                record = EvidenceRecord.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                raise ValueError(f"{source}:{line_number}: {exc}") from exc
            if record.evidence_id in seen:
                raise ValueError(f"{source}:{line_number}: duplicate evidence_id {record.evidence_id}")
            seen.add(record.evidence_id)
            records.append(record)
    if not records:
        raise ValueError(f"{source}: no evidence records")
    return records
