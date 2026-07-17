from __future__ import annotations

import unittest

from KBQA.entity_normalizer import EntityNormalizer


class EntityNormalizerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.normalizer = EntityNormalizer.__new__(EntityNormalizer)
        self.normalizer.threshold = 80
        self.normalizer.deny_words = []
        self.normalizer.type_to_names = {
            "disease": {"禽流感", "流感病毒肺炎", "嗜血流感杆菌的皮肤感染", "高血压"}
        }
        self.normalizer.name_to_types = {
            name: ["disease"] for name in self.normalizer.type_to_names["disease"]
        }

    def test_ambiguous_short_entity_is_not_expanded_arbitrarily(self) -> None:
        result = self.normalizer.normalize([{"name": "流感", "type": "disease"}])
        self.assertEqual(result["entity_dict"], {})

    def test_exact_entity_still_matches(self) -> None:
        result = self.normalizer.normalize([{"name": "高血压", "type": "disease"}])
        self.assertEqual(result["entity_dict"], {"disease": ["高血压"]})


if __name__ == "__main__":
    unittest.main()
