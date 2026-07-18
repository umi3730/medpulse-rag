"""Idempotently import curated evidence records into Neo4j."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from knowledge_graph.evidence_loader import load_evidence_records  # noqa: E402
from neo4j_client import Neo4jGraph  # noqa: E402
import settings  # noqa: E402


UPSERT_CYPHER = """
UNWIND $records AS item
MATCH (d:Disease {name: item.disease})
MERGE (e:EvidenceClaim {evidence_id: item.evidence_id})
SET e.predicate = item.predicate,
    e.claim = item.claim,
    e.source_name = item.source_name,
    e.source_url = item.source_url,
    e.publisher = item.publisher,
    e.document_title = item.document_title,
    e.published_at = item.published_at,
    e.accessed_at = item.accessed_at,
    e.evidence_level = item.evidence_level,
    e.review_status = item.review_status,
    e.section = item.section,
    e.locator = item.locator,
    e.reviewer = item.reviewer,
    e.reviewed_at = item.reviewed_at,
    e.notes = item.notes
MERGE (d)-[:HAS_EVIDENCE {predicate: item.predicate}]->(e)
MERGE (s:EvidenceSource {source_url: item.source_url})
SET s.source_name = item.source_name,
    s.publisher = item.publisher,
    s.document_title = item.document_title,
    s.published_at = item.published_at
MERGE (e)-[:FROM_SOURCE]->(s)
RETURN count(e) AS imported
"""


def import_records(graph: Neo4jGraph, records) -> int:
    result = graph.run(UPSERT_CYPHER, records=[record.to_dict() for record in records]).data()
    return int(result[0]["imported"]) if result else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or import curated medical evidence.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true", help="Write validated records to Neo4j.")
    args = parser.parse_args()
    records = load_evidence_records(args.path)
    print(json.dumps({"valid": True, "record_count": len(records)}, ensure_ascii=False))
    if not args.apply:
        return
    graph = Neo4jGraph(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        name=settings.NEO4J_DATABASE,
    )
    try:
        print(json.dumps({"imported": import_records(graph, records)}, ensure_ascii=False))
    finally:
        graph.close()


if __name__ == "__main__":
    main()
