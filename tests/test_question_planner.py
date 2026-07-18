from __future__ import annotations

import unittest

from graphrag.question_planner import QuestionPlanner


class QuestionPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = QuestionPlanner()

    def test_cause_uses_only_cause_property(self) -> None:
        plan = self.planner.plan("糖尿病可能由哪些原因引起？")
        self.assertEqual(plan.intent, "cause")
        self.assertEqual(plan.requested_fields, ["cause"])
        self.assertEqual(plan.relation_filters, [])

    def test_complication_maps_to_graph_relation(self) -> None:
        plan = self.planner.plan("糖尿病可能有哪些并发症？")
        self.assertEqual(plan.intent, "complication")
        self.assertEqual(plan.relation_filters, ["acompany_with"])

    def test_drug_dosage_is_high_risk(self) -> None:
        plan = self.planner.plan("阿莫西林应该吃多少剂量？")
        self.assertEqual(plan.intent, "drug")
        self.assertEqual(plan.risk_level, "high")

    def test_ambiguous_pronoun_requires_context(self) -> None:
        without_memory = self.planner.plan("这个病怎么治疗？")
        with_memory = self.planner.plan("这个病怎么治疗？", has_memory_entities=True)
        self.assertTrue(without_memory.needs_clarification)
        self.assertFalse(with_memory.needs_clarification)

    def test_detail_level_is_explicit(self) -> None:
        self.assertEqual(self.planner.plan("简单说说高血压").detail_level, "brief")
        self.assertEqual(self.planner.plan("详细说说高血压").detail_level, "detailed")

    def test_food_and_exercise_also_requests_preventive_evidence(self) -> None:
        plan = self.planner.plan("高血压患者日常饮食和运动需要注意什么？")
        self.assertEqual(plan.intents, ["food", "lifestyle"])
        self.assertEqual(
            plan.requested_fields,
            ["do_eat", "no_eat", "recommand_eat", "prevent"],
        )
        self.assertEqual(
            plan.relation_filters,
            ["do_eat", "no_eat", "recommand_eat"],
        )


if __name__ == "__main__":
    unittest.main()
