#!/usr/bin/env python3
# coding: utf-8
"""
答案格式化：将 Neo4j 查询结果转换为自然语言回答。

模式：
  - template: 确定性模板（默认，快速）
  - llm: 模板 + LLM 润色（更自然，需 Ollama）
"""
from __future__ import annotations

import re
import logging

from config import ANSWER_NUM_LIMIT

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN_CORE = True
except ImportError:
    HAS_LANGCHAIN_CORE = False

log = logging.getLogger("qa")

POLISH_SYSTEM_PROMPT = (
    "你是医疗问答助手。请将以下结构化回答改写为自然流畅的中文，"
    "保留所有医学信息，不要添加未提及的内容。直接输出改写后的文本。"
    "/no_think"
)


class AnswerFormatter:
    """格式化 Neo4j 查询结果为中文自然语言回答。"""

    def __init__(self, mode: str = "template", llm=None,
                 num_limit: int = ANSWER_NUM_LIMIT):
        self.mode = mode
        self.llm = llm if mode == "llm" else None
        self.num_limit = num_limit

    def format(self, result_groups: list[dict]) -> str:
        """格式化所有查询结果组为单一回答字符串。"""
        parts = []
        for group in result_groups:
            question_type = group["question_type"]
            answers = group["answers"]
            text = self._template_format(question_type, answers)
            if text:
                parts.append(text)

        if not parts:
            return ""

        combined = "\n".join(parts)

        # LLM 润色
        if self.mode == "llm" and self.llm:
            polished = self._llm_polish(combined)
            if polished:
                return polished

        return combined

    # ------------------------------------------------------------------
    # 18 种模板（移植自 answer_search.py，保留原有措辞）
    # ------------------------------------------------------------------
    def _template_format(self, question_type: str, answers: list[dict]) -> str:
        if not answers:
            return ""

        n = self.num_limit

        if question_type == "disease_symptom":
            desc = [i["n.name"] for i in answers if i.get("n.name")]
            subject = answers[0].get("m.name", "")
            return "{}的症状包括：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "symptom_disease":
            desc = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("n.name", "")
            return "症状{}可能染上的疾病有：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_cause":
            desc = [i["m.cause"] for i in answers if i.get("m.cause")]
            subject = answers[0].get("m.name", "")
            return "{}可能的成因有：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_prevent":
            desc = [i["m.prevent"] for i in answers if i.get("m.prevent")]
            subject = answers[0].get("m.name", "")
            return "{}的预防措施包括：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_lasttime":
            desc = [i["m.cure_lasttime"] for i in answers if i.get("m.cure_lasttime")]
            subject = answers[0].get("m.name", "")
            return "{}治疗可能持续的周期为：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_cureway":
            desc = []
            for i in answers:
                v = i.get("m.cure_way")
                if isinstance(v, list):
                    desc.append(";".join(v))
                elif v:
                    desc.append(str(v))
            subject = answers[0].get("m.name", "")
            return "{}可以尝试如下治疗：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_cureprob":
            desc = [i["m.cured_prob"] for i in answers if i.get("m.cured_prob")]
            subject = answers[0].get("m.name", "")
            return "{}治愈的概率为（仅供参考）：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_easyget":
            desc = [i["m.easy_get"] for i in answers if i.get("m.easy_get")]
            subject = answers[0].get("m.name", "")
            return "{}的易感人群包括：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_desc":
            desc = [i["m.desc"] for i in answers if i.get("m.desc")]
            subject = answers[0].get("m.name", "")
            return "{}，熟悉一下：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_acompany":
            desc1 = [i["n.name"] for i in answers if i.get("n.name")]
            desc2 = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("m.name", "")
            desc = [i for i in desc1 + desc2 if i != subject]
            return "{}的并发症包括：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_not_food":
            desc = [i["n.name"] for i in answers if i.get("n.name")]
            subject = answers[0].get("m.name", "")
            return "{}忌食的食物包括有：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_do_food":
            do_desc = [i["n.name"] for i in answers if i.get("r.name") == "宜吃" and i.get("n.name")]
            rec_desc = [i["n.name"] for i in answers if i.get("r.name") == "推荐食谱" and i.get("n.name")]
            subject = answers[0].get("m.name", "")
            return "{}宜食的食物包括有：{}\n推荐食谱包括有：{}".format(
                subject,
                ";".join(list(set(do_desc))[:n]),
                ";".join(list(set(rec_desc))[:n]),
            )

        if question_type == "food_not_disease":
            desc = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("n.name", "")
            return "患有{}的人最好不要吃{}".format("；".join(list(set(desc))[:n]), subject)

        if question_type == "food_do_disease":
            desc = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("n.name", "")
            return "患有{}的人建议多试试{}".format("；".join(list(set(desc))[:n]), subject)

        if question_type == "disease_drug":
            desc = [i["n.name"] for i in answers if i.get("n.name")]
            subject = answers[0].get("m.name", "")
            return "{}通常使用的药品包括：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "drug_disease":
            desc = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("n.name", "")
            return "{}主治的疾病有{}，可以试试".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "disease_check":
            desc = [i["n.name"] for i in answers if i.get("n.name")]
            subject = answers[0].get("m.name", "")
            return "{}通常可以通过以下方式检查出来：{}".format(subject, "；".join(list(set(desc))[:n]))

        if question_type == "check_disease":
            desc = [i["m.name"] for i in answers if i.get("m.name")]
            subject = answers[0].get("n.name", "")
            return "通常可以通过{}检查出来的疾病有{}".format(subject, "；".join(list(set(desc))[:n]))

        log.warning("未知的问题类型: %s", question_type)
        return ""

    # ------------------------------------------------------------------
    # LLM 润色
    # ------------------------------------------------------------------
    def _llm_polish(self, text: str) -> str:
        """用 LLM 将模板回答改写为更自然的语言。"""
        if not self.llm or not HAS_LANGCHAIN_CORE:
            return ""
        try:
            messages = [
                SystemMessage(content=POLISH_SYSTEM_PROMPT),
                HumanMessage(content=text),
            ]
            resp = self.llm.invoke(messages)
            content = resp.content or ""
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            return content if content else ""
        except Exception as e:
            log.debug("LLM 润色失败: %s", e)
            return ""
