from __future__ import annotations

import unittest

from graphrag.generator import (
    GraphRAGGenerator,
    build_safe_fallback_answer,
    sanitize_grounded_answer,
)


class GeneratorPromptTests(unittest.TestCase):
    def test_grounding_filter_removes_uncited_medical_claim(self) -> None:
        answer = sanitize_grounded_answer(
            "高血压可能伴随头痛 [1]。感冒通常由病毒感染引起。"
        )
        self.assertEqual(answer, "高血压可能伴随头痛 [1]。")

    def test_grounding_filter_keeps_citation_range(self) -> None:
        answer = sanitize_grounded_answer("可见症状包括头痛、头晕 [1]-[4]。")
        self.assertEqual(answer, "可见症状包括头痛、头晕 [1]-[4]。")

    def test_high_risk_dosage_fallback_is_not_prescriptive(self) -> None:
        answer = build_safe_fallback_answer(
            "降压药效果不好，我可以自己加量吗？",
            {"intents": ["drug"], "risk_level": "high"},
        )
        self.assertIn("加量", answer)
        self.assertIn("联系开药医生", answer)
        self.assertNotIn("可以自行加量", answer)

    def test_high_risk_stop_fallback_blocks_unsupervised_change(self) -> None:
        answer = build_safe_fallback_answer(
            "血压正常了能马上停药吗？",
            {"intents": ["drug"], "risk_level": "high"},
        )
        self.assertIn("停药前", answer)
        self.assertIn("不要擅自停用", answer)
        self.assertNotIn("马上停药", answer)

    def test_low_risk_fallback_names_requested_topic(self) -> None:
        answer = build_safe_fallback_answer(
            "如何预防高血压？",
            {"intents": ["prevent"], "risk_level": "low"},
        )
        self.assertIn("预防", answer)
        self.assertNotIn("您好", answer)

    def test_brief_low_risk_prompt_avoids_fixed_disclaimer(self) -> None:
        prompt = GraphRAGGenerator.build_prompt(
            "【Disease】高血压\n  病因: 测试证据",
            {
                "intent": "cause",
                "requested_fields": ["cause"],
                "detail_level": "brief",
                "risk_level": "low",
            },
        )
        self.assertIn("病因(cause)", prompt)
        self.assertIn("使用 1 至 3 句话回答", prompt)
        self.assertIn("无需机械添加就医免责声明", prompt)
        self.assertNotIn("以上信息仅供参考，具体请咨询专业医生", prompt)

    def test_high_risk_prompt_blocks_actionable_dosage_changes(self) -> None:
        prompt = GraphRAGGenerator.build_prompt(
            "药物证据",
            {
                "intent": "drug",
                "requested_fields": ["common_drug"],
                "detail_level": "standard",
                "risk_level": "high",
            },
        )
        self.assertIn("高风险问题", prompt)
        self.assertIn("不要给出可直接执行的处方或剂量调整", prompt)

    def test_memory_is_not_treated_as_medical_evidence(self) -> None:
        prompt = GraphRAGGenerator.build_prompt(
            "[Conversation Memory]\n上一轮回答",
            {"intent": "general", "requested_fields": ["desc"]},
        )
        self.assertIn("不能作为医学事实依据", prompt)
        self.assertIn("上一轮回答", prompt)

    def test_prompt_requires_inline_evidence_citations(self) -> None:
        prompt = GraphRAGGenerator.build_prompt(
            "【Disease】高血压\n  症状: 头痛 [1]",
            {"intent": "symptom", "requested_fields": ["has_symptom"]},
        )
        self.assertIn("事实陈述都必须紧跟对应编号", prompt)
        self.assertIn("只能使用证据中已经出现的编号", prompt)


if __name__ == "__main__":
    unittest.main()
