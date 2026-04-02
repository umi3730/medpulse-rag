#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 实体抽取器：使用 LLM 从问句中提取医疗实体（不做意图分类）。
"""
from __future__ import annotations

import json
import logging
import re

from config import ENTITY_EXTRACT_PROMPT

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

log = logging.getLogger("graphrag")

_VALID_ENTITY_TYPES = {"disease", "symptom", "drug", "check", "food", "department", "producer"}


class EntityExtractor:
    """从问句中提取医疗实体（仅实体，不含意图）。"""

    def __init__(self, llm: ChatOllama | None = None):
        self.llm = llm

    @property
    def available(self) -> bool:
        return self.llm is not None and HAS_LANGCHAIN

    def extract(self, question: str) -> list[dict] | None:
        """
        抽取实体。

        返回: [{"name": "糖尿病", "type": "disease"}, ...] 或 None（失败时）
        """
        if not self.available:
            return None
        try:
            messages = [
                SystemMessage(content=ENTITY_EXTRACT_PROMPT),
                HumanMessage(content=question),
            ]
            resp = self.llm.invoke(messages)
            content = resp.content or ""
            return self._parse(content)
        except Exception as e:
            log.warning("实体抽取 LLM 调用异常: %s", e)
            return None

    def _parse(self, content: str) -> list[dict] | None:
        """解析 LLM 输出的 JSON。"""
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            return None
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return None

        raw = data.get("entities", [])
        if not isinstance(raw, list):
            return None

        entities = []
        for ent in raw:
            if isinstance(ent, dict) and ent.get("name"):
                etype = ent.get("type", "")
                if etype not in _VALID_ENTITY_TYPES:
                    etype = ""
                entities.append({"name": ent["name"].strip(), "type": etype})
        return entities if entities else None
