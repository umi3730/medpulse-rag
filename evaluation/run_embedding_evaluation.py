#!/usr/bin/env python3
"""Compare embedding providers on a small paraphrase-retrieval dataset."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from graphrag.embedding_provider import create_embedding_provider


DEFAULT_DATASET = Path(__file__).with_name("embedding_cases.json")


def dot(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="sentence_transformers")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    provider = create_embedding_provider(args.provider, fallback_to_hash=False)
    documents = dataset["documents"]
    document_vectors = {
        item["id"]: provider.embed_document(item["text"])
        for item in documents
    }

    reciprocal_ranks: list[float] = []
    top1_hits = 0
    results = []
    for case in dataset["queries"]:
        query_vector = provider.embed_query(case["query"])
        ranking = sorted(
            (
                {"id": item["id"], "score": dot(query_vector, document_vectors[item["id"]])}
                for item in documents
            ),
            key=lambda item: item["score"],
            reverse=True,
        )
        rank = next(
            index for index, item in enumerate(ranking, start=1)
            if item["id"] == case["expected_id"]
        )
        top1_hits += int(rank == 1)
        reciprocal_ranks.append(1 / rank)
        results.append({
            "query": case["query"],
            "expected_id": case["expected_id"],
            "rank": rank,
            "top_result": ranking[0],
        })

    count = len(results)
    report = {
        "provider": provider.name,
        "model": provider.model_name,
        "dimension": provider.dimension,
        "query_count": count,
        "recall_at_1": round(top1_hits / count, 4),
        "mrr": round(sum(reciprocal_ranks) / count, 4),
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
