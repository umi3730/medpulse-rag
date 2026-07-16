#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 实体抽取器：使用 LLM 从问句中提取医疗实体（不做意图分类）。
"""
from __future__ import annotations

import json
import logging
import re

from .config import ENTITY_DICTS, ENTITY_EXTRACT_PROMPT

try:
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN_CORE = True
except ImportError:
    HAS_LANGCHAIN_CORE = False

log = logging.getLogger("graphrag")

_VALID_ENTITY_TYPES = {"disease", "symptom", "drug", "check", "food", "department", "producer"}


class EntityExtractor:
    """从问句中提取医疗实体（仅实体，不含意图）。"""

    def __init__(self, llm=None):
        self.llm = llm
        self._dict_entities = self._load_dict_entities()

    @property
    def available(self) -> bool:
        return self.llm is not None and HAS_LANGCHAIN_CORE

    def extract(self, question: str) -> list[dict] | None:
        """
        抽取实体。

        返回: [{"name": "糖尿病", "type": "disease"}, ...] 或 None（失败时）
        """
        question = question.strip()
        if not question:
            return None

        if not self.available:
            return self._fallback_extract(question)
        try:
            messages = [
                SystemMessage(content=ENTITY_EXTRACT_PROMPT),
                HumanMessage(content=question),
            ]
            resp = self.llm.invoke(messages)
            content = resp.content or ""
            parsed = self._parse(content)
            return parsed or self._fallback_extract(question)
        except Exception as e:
            log.warning("实体抽取 LLM 调用异常: %s", e)
            return self._fallback_extract(question)

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

    @staticmethod
    def _load_dict_entities() -> list[tuple[str, str]]:
        """加载本地实体词典，用作 LLM 抽取失败时的兜底。"""
        entities: list[tuple[str, str]] = []
        for etype, fpath in ENTITY_DICTS.items():
            if not fpath.exists():
                continue
            with open(fpath, encoding="utf-8") as fh:
                for line in fh:
                    name = line.strip()
                    if len(name) >= 2:
                        entities.append((name, etype))

        # 长词优先，避免“糖”之类短词抢走“糖尿病”。
        entities.sort(key=lambda item: len(item[0]), reverse=True)
        return entities

    def _fallback_extract(self, question: str) -> list[dict] | None:
        """基于本地词典做最长子串匹配，避免 GraphRAG 因 JSON 抽取失败直接兜底。"""
        matched: list[dict] = []
        occupied: list[tuple[int, int]] = []

        for name, etype in self._dict_entities:
            start = question.find(name)
            if start < 0:
                continue
            end = start + len(name)
            if any(not (end <= a or start >= b) for a, b in occupied):
                continue
            matched.append({"name": name, "type": etype})
            occupied.append((start, end))
            if len(matched) >= 8:
                break

        if matched:
            log.info("实体抽取使用本地词典兜底: %s", matched)
        return matched or None
