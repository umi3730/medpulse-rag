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


class GraphRAGGenerator:
    """基于图谱上下文的 LLM 答案生成。"""

    def __init__(self, llm=None):
        self.llm = llm

    @property
    def available(self) -> bool:
        return self.llm is not None and HAS_LANGCHAIN_CORE

    def generate(self, question: str, context_text: str) -> dict:
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

        system_prompt = GENERATION_SYSTEM_PROMPT.format(context=context_text)

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

    def stream(self, question: str, context_text: str):
        """流式生成回答，yield 文本 chunk；最后 yield dict 表示结束。"""
        if not self.available or not context_text:
            return

        system_prompt = GENERATION_SYSTEM_PROMPT.format(context=context_text)
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
