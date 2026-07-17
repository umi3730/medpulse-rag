#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 答案生成器：将问题 + 图谱上下文发给 LLM，生成综合回答。
"""
from __future__ import annotations

import logging
import re
import time

from .config import GENERATION_SYSTEM_PROMPT

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN_CORE = True
except ImportError:
    HAS_LANGCHAIN_CORE = False

log = logging.getLogger("graphrag")

FIELD_LABELS = {
    "desc": "疾病简介",
    "cause": "病因",
    "prevent": "预防",
    "cure_way": "治疗方式",
    "cure_lasttime": "治疗周期",
    "cured_prob": "治愈率",
    "easy_get": "易感人群",
    "cost_money": "治疗费用",
    "has_symptom": "症状",
    "acompany_with": "并发症",
    "need_check": "检查项目",
    "common_drug": "常用药物",
    "recommand_drug": "推荐药物",
    "do_eat": "宜吃食物",
    "no_eat": "忌口食物",
    "recommand_eat": "推荐食谱",
    "belongs_to": "就诊科室",
    "dept_belongs_to": "上级科室",
}


def build_safe_fallback_answer(question: str, query_plan: dict | None = None) -> str:
    """Return a deterministic answer when graph evidence or generation is unavailable."""
    plan = query_plan or {}
    risk_level = plan.get("risk_level", "low")
    intents = set(plan.get("intents") or [plan.get("intent", "general")])

    if risk_level == "high":
        if "停药" in question:
            return (
                "停药前应先联系开药医生评估；即使当前指标恢复正常，也不要擅自停用药物。"
                "如果已经出现明显不适，请及时就医。"
            )
        if any(term in question for term in ("加量", "减量", "剂量")):
            return (
                "加量或调整剂量前应先联系开药医生，不要自行改变用法。"
                "若症状加重或出现明显不适，请及时就医。"
            )
        return "这属于高风险健康问题，不要自行处置；请尽快联系医生，情况紧急时立即呼叫急救。"

    intent_labels = {
        "cause": "病因", "complication": "并发症", "symptom": "症状",
        "check": "检查", "drug": "用药", "food": "饮食",
        "department": "就诊科室", "prevent": "预防", "treatment": "治疗",
        "duration": "治疗时间", "cure_rate": "预后", "susceptible": "易感人群",
        "cost": "费用",
    }
    topics = [intent_labels[intent] for intent in intents if intent in intent_labels]
    topic = "和".join(topics) if topics else "这个问题"
    return f"现有图谱证据不足以可靠回答{topic}。请补充具体疾病名称或换一种问法。"


class GraphRAGGenerator:
    """基于图谱上下文的 LLM 答案生成。"""

    def __init__(self, llm=None):
        self.llm = llm

    @property
    def available(self) -> bool:
        return self.llm is not None and HAS_LANGCHAIN_CORE

    def generate(
        self,
        question: str,
        context_text: str,
        query_plan: dict | None = None,
        conversation_context: str = "",
    ) -> dict:
        """
        生成回答。

        返回:
          {
            "answer": str,
            "generation_time_ms": float,
            "model_used": str,
          }
        """
        if not self.available or not context_text:
            return {"answer": "", "generation_time_ms": 0, "model_used": "none"}

        system_prompt = self.build_prompt(
            context_text, query_plan, conversation_context=conversation_context
        )

        t0 = time.time()
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=question),
            ]
            resp = self.llm.invoke(messages)
            content = resp.content or ""
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
            elapsed = (time.time() - t0) * 1000
            return {
                "answer": content,
                "generation_time_ms": round(elapsed, 1),
                "model_used": getattr(self.llm, "model", "unknown"),
            }
        except Exception as e:
            log.error("GraphRAG 生成失败: %s", e)
            elapsed = (time.time() - t0) * 1000
            return {
                "answer": "",
                "generation_time_ms": round(elapsed, 1),
                "model_used": "error",
            }

    def stream(
        self,
        question: str,
        context_text: str,
        query_plan: dict | None = None,
        conversation_context: str = "",
    ):
        """流式生成回答，yield 文本 chunk；最后 yield dict 表示结束。"""
        if not self.available or not context_text:
            return

        system_prompt = self.build_prompt(
            context_text, query_plan, conversation_context=conversation_context
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=question),
        ]

        t0 = time.time()
        in_think = False
        try:
            for chunk in self.llm.stream(messages):
                text = chunk.content or ""
                if "<think>" in text:
                    in_think = True
                if in_think:
                    if "</think>" in text:
                        in_think = False
                        text = text.split("</think>", 1)[1]
                    else:
                        continue
                if text:
                    yield text
        except Exception as e:
            log.error("GraphRAG 流式生成失败: %s", e)

        elapsed = round((time.time() - t0) * 1000, 1)
        yield {"generation_time_ms": elapsed, "model_used": getattr(self.llm, "model", "unknown")}

    @staticmethod
    def build_prompt(
        context_text: str,
        query_plan: dict | None = None,
        *,
        conversation_context: str = "",
    ) -> str:
        plan = query_plan or {}
        detail_level = plan.get("detail_level", "standard")
        detail_instruction = {
            "brief": "使用 1 至 3 句话回答，不添加标题。",
            "detailed": "在证据允许的范围内分点说明，但每一点都必须与所问内容直接相关。",
            "standard": "优先使用一个短段落；确有多个并列要点时再使用简短列表。",
        }.get(detail_level, "优先使用一个短段落回答。")
        risk_level = plan.get("risk_level", "low")
        risk_instruction = {
            "high": "这是高风险问题。不要给出可直接执行的处方或剂量调整；必要时明确建议及时就医或联系急救。",
            "medium": "这是需要谨慎表达的问题。区分知识事实与个体化医疗建议，并给出一句必要的安全边界。",
            "low": "这是一般知识问题，无需机械添加就医免责声明。",
        }.get(risk_level, "按一般知识问题处理。")
        fields = plan.get("requested_fields") or []
        fields_text = (
            "、".join(f"{FIELD_LABELS.get(str(field), field)}({field})" for field in fields)
            if fields else "未指定"
        )
        plan_instructions = "\n".join([
            f"- 主要意图：{plan.get('intent', 'general')}",
            f"- 仅回答字段：{fields_text}",
            f"- 表达粒度：{detail_level}。{detail_instruction}",
            f"- 风险等级：{risk_level}。{risk_instruction}",
        ])
        return GENERATION_SYSTEM_PROMPT.format(
            plan_instructions=plan_instructions,
            conversation_context=conversation_context or "无",
            context=context_text,
        )
