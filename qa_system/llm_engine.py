#!/usr/bin/env python3
# coding: utf-8
"""
LLM 语义分析引擎：单次调用同时完成意图识别 + 实体抽取。

使用 LangChain + Ollama (qwen3:8b)，输出结构化 JSON。
"""
from __future__ import annotations

import json
import re
import logging

from config import (
    LLM_SYSTEM_PROMPT, OLLAMA_MODEL, OLLAMA_BASE_URL,
    LLM_TEMPERATURE, LLM_NUM_PREDICT, INTENT_TYPES,
)

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

log = logging.getLogger("qa")

# LLM 有效意图集合
_VALID_INTENTS = set(INTENT_TYPES.keys())
_VALID_ENTITY_TYPES = {"disease", "symptom", "drug", "check", "food", "department", "producer"}


class LLMEngine:
    """
    LLM 意图识别 + 实体抽取引擎。

    单次 LLM 调用输出：
      {"intents": [...], "entities": [{"name": ..., "type": ...}], "has_negation": bool}
    失败时返回 None，由调用方触发降级。
    """

    def __init__(self, model: str = OLLAMA_MODEL, base_url: str = OLLAMA_BASE_URL):
        self.llm = None
        self.model = model
        self.base_url = base_url
        if not HAS_LANGCHAIN:
            log.warning("langchain_ollama 未安装，LLM 引擎不可用")
            return
        try:
            self.llm = ChatOllama(
                model=model,
                base_url=base_url,
                temperature=LLM_TEMPERATURE,
                num_predict=LLM_NUM_PREDICT,
            )
            # 连通性测试
            self.llm.invoke("hi")
            log.info("Ollama (%s) 连接成功，LLM 引擎就绪", model)
        except Exception as e:
            log.warning("Ollama 不可用 (%s)，LLM 引擎将降级", e)
            self.llm = None

    @property
    def available(self) -> bool:
        return self.llm is not None

    def analyze(self, question: str) -> dict | None:
        """
        分析用户问题，返回结构化结果。

        返回: {"intents": [...], "entities": [...], "has_negation": bool}
        失败返回 None。
        """
        if not self.llm:
            return None
        try:
            messages = [
                SystemMessage(content=LLM_SYSTEM_PROMPT),
                HumanMessage(content=question),
            ]
            resp = self.llm.invoke(messages)
            content = resp.content or ""
            return self._parse_response(content)
        except Exception as e:
            log.warning("LLM 调用异常: %s", e)
            return None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------
    def _parse_response(self, content: str) -> dict | None:
        """解析 LLM 响应 JSON。"""
        # 去掉 qwen3 的 <think>...</think>
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        # 尝试提取 JSON（可能被 markdown 代码块包裹）
        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            log.debug("LLM 响应中未找到 JSON: %s", content[:200])
            return None
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            log.debug("JSON 解析失败: %s | 内容: %s", e, content[:200])
            return None

        return self._validate(data)

    @staticmethod
    def _validate(data: dict) -> dict | None:
        """校验并清理 LLM 输出。"""
        if not isinstance(data, dict):
            return None

        # 意图
        raw_intents = data.get("intents", [])
        if not isinstance(raw_intents, list):
            raw_intents = []
        intents = [i for i in raw_intents if i in _VALID_INTENTS]

        # 实体
        raw_entities = data.get("entities", [])
        if not isinstance(raw_entities, list):
            raw_entities = []
        entities = []
        for ent in raw_entities:
            if isinstance(ent, dict) and ent.get("name"):
                etype = ent.get("type", "")
                if etype not in _VALID_ENTITY_TYPES:
                    etype = ""
                entities.append({"name": ent["name"].strip(), "type": etype})

        # 否定
        has_negation = bool(data.get("has_negation", False))

        if not intents and not entities:
            return None

        return {
            "intents": intents,
            "entities": entities,
            "has_negation": has_negation,
        }
