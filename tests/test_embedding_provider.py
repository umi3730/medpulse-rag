from __future__ import annotations

import math
import unittest

from graphrag.embedding_provider import HashEmbeddingProvider, create_embedding_provider
from graphrag.vector_store import QdrantVectorStore


class EmbeddingProviderTests(unittest.TestCase):
    def test_hash_provider_is_normalized_and_deterministic(self) -> None:
        provider = HashEmbeddingProvider(dimension=64)
        first = provider.embed_document("高血压症状")
        second = provider.embed_document("高血压症状")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)
        self.assertAlmostEqual(math.sqrt(sum(value * value for value in first)), 1.0)

    def test_hash_factory_remains_available_as_explicit_fallback(self) -> None:
        provider = create_embedding_provider("hash", fallback_to_hash=False)
        self.assertEqual(provider.name, "hash")
        self.assertEqual(provider.dimension, 384)

    def test_unknown_provider_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported embedding provider"):
            create_embedding_provider("unknown", fallback_to_hash=False)

    def test_collection_name_isolated_by_provider_model_and_dimension(self) -> None:
        store = QdrantVectorStore.__new__(QdrantVectorStore)
        store.embedding_provider = HashEmbeddingProvider(dimension=64)
        name = store._provider_collection_name()
        self.assertIn("hash", name)
        self.assertIn("64", name)


if __name__ == "__main__":
    unittest.main()
