#!/usr/bin/env python3
# coding: utf-8
"""
并发症文本分词模块

三级降级策略：
  1) LLM (LangChain + Ollama) — 语义理解，效果最优
  2) 词典最大双向匹配 (dict/disease.txt) — 无 LLM 时使用
  3) 简单分隔符切分 — 兜底
"""

import re
import logging
from pathlib import Path

try:
    from langchain_ollama import ChatOllama
    from langchain_core.messages import HumanMessage, SystemMessage
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

log = logging.getLogger("spider")

ACOMPANY_SYSTEM_PROMPT = (
    "你是医学文本处理助手。用户会给你一段并发症文本，"
    "请将其中的疾病名称逐个提取出来。"
    "要求：每行输出一个疾病名称，不要输出序号、标点或任何其他内容。"
    "/no_think"
)


# ---------------------------------------------------------------------------
# Level 2: 词典最大双向匹配
# ---------------------------------------------------------------------------
class DictCutter:
    """基于词典的最大双向匹配分词。"""

    def __init__(self, dict_path):
        self.word_dict = set()
        self.max_wordlen = 0
        if dict_path.exists():
            for line in open(dict_path, encoding="utf-8"):
                wd = line.strip()
                if wd:
                    self.word_dict.add(wd)
                    self.max_wordlen = max(self.max_wordlen, len(wd))
        if self.max_wordlen == 0:
            self.max_wordlen = 5

    @property
    def available(self):
        return len(self.word_dict) > 0

    def cut(self, sent):
        """最大双向匹配，返回切分结果（取粒度更优的一侧）。"""
        fwd = self._forward(sent)
        bwd = self._backward(sent)
        single = lambda wl: sum(1 for w in wl if len(w) == 1)
        if len(fwd) == len(bwd):
            return bwd if single(fwd) > single(bwd) else fwd
        return fwd if len(bwd) > len(fwd) else bwd

    def _forward(self, sent):
        result, idx = [], 0
        while idx < len(sent):
            matched = False
            for size in range(self.max_wordlen, 0, -1):
                cand = sent[idx: idx + size]
                if cand in self.word_dict:
                    result.append(cand)
                    idx += size
                    matched = True
                    break
            if not matched:
                result.append(sent[idx])
                idx += 1
        return result

    def _backward(self, sent):
        result, idx = [], len(sent)
        while idx > 0:
            matched = False
            for size in range(self.max_wordlen, 0, -1):
                start = idx - size
                if start < 0:
                    continue
                cand = sent[start: idx]
                if cand in self.word_dict:
                    result.append(cand)
                    idx = start
                    matched = True
                    break
            if not matched:
                result.append(sent[idx - 1])
                idx -= 1
        return result[::-1]


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
class LLMWordSplitter:
    """
    三级降级并发症分词：
      1) LLM (LangChain + Ollama) — 最优
      2) 词典匹配 (dict/disease.txt) — 无 LLM 时使用
      3) 简单分隔符切分 — 兜底
    """

    def __init__(self, model="qwen3:8b", base_url="http://localhost:11434",
                 dict_path=None):
        self.llm = None
        self.model = model
        # 加载词典（第二级降级）
        if dict_path is None:
            dict_path = Path(__file__).resolve().parent.parent / "dict" / "disease.txt"
        self.dict_cutter = DictCutter(dict_path)
        if self.dict_cutter.available:
            log.info("疾病词典已加载 (%d 词条)，可用于降级分词", len(self.dict_cutter.word_dict))
        # 初始化 LLM（第一级）
        if not HAS_LANGCHAIN:
            log.warning("langchain_ollama 未安装，将使用词典/简单分割")
            return
        try:
            self.llm = ChatOllama(
                model=model,
                base_url=base_url,
                temperature=0,
                num_predict=256,
            )
            # 轻量连通性测试
            self.llm.invoke("hi")
            log.info("Ollama (%s) 连接成功，将使用 LLM 分词", model)
        except Exception as e:
            log.warning("Ollama 不可用 (%s)，将使用词典/简单分割", e)
            self.llm = None

    # ------------------------------------------------------------------
    def split(self, text):
        """切分并发症文本，返回疾病名称列表（过滤单字）。"""
        if not text or not text.strip():
            return []
        # Level 1: LLM
        if self.llm:
            try:
                result = self._llm_split(text)
                if result:
                    return result
            except Exception as e:
                log.debug("LLM 分词异常: %s，降级处理", e)
        # Level 2: 词典匹配
        if self.dict_cutter.available:
            return [w for w in self.dict_cutter.cut(text) if len(w) > 1]
        # Level 3: 简单分隔符
        return self._simple_split(text)

    # ------------------------------------------------------------------
    def _llm_split(self, text):
        messages = [
            SystemMessage(content=ACOMPANY_SYSTEM_PROMPT),
            HumanMessage(content=text),
        ]
        resp = self.llm.invoke(messages)
        content = resp.content or ""
        # qwen3 可能输出 <think>...</think>，去掉
        content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
        names = []
        for line in content.split("\n"):
            w = line.strip().strip("-").strip("•").strip("*").strip()
            if w and len(w) > 1:
                names.append(w)
        return names

    # ------------------------------------------------------------------
    @staticmethod
    def _simple_split(text):
        """兜底：按常见分隔符拆分。"""
        for sep in ["、", "，", ",", "；", ";"]:
            if sep in text:
                return [w.strip() for w in text.split(sep) if len(w.strip()) > 1]
        parts = text.split()
        if len(parts) > 1:
            return [w for w in parts if len(w) > 1]
        return [text] if len(text) > 1 else []
