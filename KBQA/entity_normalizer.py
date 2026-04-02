#!/usr/bin/env python3
# coding: utf-8
"""
实体归一化：将 LLM 抽取的实体名映射为 Neo4j 中的规范名称。

三级匹配策略：
  1) 精确匹配（O(1) set lookup）
  2) 子串包含匹配
  3) 模糊匹配（rapidfuzz / difflib 降级）
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import ENTITY_DICTS, DENY_DICT_PATH, FUZZY_MATCH_THRESHOLD

try:
    from rapidfuzz import fuzz as rf_fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

log = logging.getLogger("qa")


class EntityNormalizer:
    """加载 dict/ 词典，将 LLM 抽取的实体归一化为图谱中的规范名称。"""

    def __init__(self, dict_dir: Path | None = None, threshold: int = FUZZY_MATCH_THRESHOLD):
        self.threshold = threshold
        # type → set[name]
        self.type_to_names: dict[str, set[str]] = {}
        # name → [type, ...]
        self.name_to_types: dict[str, list[str]] = {}
        # 否定词
        self.deny_words: list[str] = []

        self._load_dicts(dict_dir)

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def _load_dicts(self, dict_dir: Path | None):
        """加载所有实体词典和否定词。"""
        for etype, fpath in ENTITY_DICTS.items():
            names = set()
            if fpath.exists():
                for line in open(fpath, encoding="utf-8"):
                    w = line.strip()
                    if w:
                        names.add(w)
            self.type_to_names[etype] = names
            for name in names:
                self.name_to_types.setdefault(name, [])
                if etype not in self.name_to_types[name]:
                    self.name_to_types[name].append(etype)
        total = sum(len(v) for v in self.type_to_names.values())
        log.info("实体词典加载完成：%d 类别，%d 词条", len(self.type_to_names), total)

        if DENY_DICT_PATH.exists():
            self.deny_words = [
                line.strip() for line in open(DENY_DICT_PATH, encoding="utf-8")
                if line.strip()
            ]

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------
    def normalize(self, entities: list[dict], has_negation: bool = False) -> dict:
        """
        归一化 LLM 抽取的实体列表。

        输入: [{"name": "糖尿病", "type": "disease"}, ...]
        输出: {
            "entity_dict": {"disease": ["糖尿病"], ...},  # 按类型分组
            "entities": {"糖尿病": ["disease"], ...},     # 兼容旧格式
        }
        """
        entity_dict: dict[str, list[str]] = {}
        entities_map: dict[str, list[str]] = {}

        for ent in entities:
            raw_name = ent.get("name", "").strip()
            expected_type = ent.get("type", "").strip()
            if not raw_name:
                continue

            matches = self._match_entity(raw_name, expected_type)
            if not matches:
                log.debug("实体 '%s' (%s) 无法归一化，跳过", raw_name, expected_type)
                continue

            for canonical_name, etype in matches:
                entity_dict.setdefault(etype, [])
                if canonical_name not in entity_dict[etype]:
                    entity_dict[etype].append(canonical_name)
                entities_map.setdefault(canonical_name, [])
                if etype not in entities_map[canonical_name]:
                    entities_map[canonical_name].append(etype)

        return {"entity_dict": entity_dict, "entities": entities_map}

    def check_negation(self, question: str) -> bool:
        """检查问句是否包含否定词（作为 LLM has_negation 的备份）。"""
        return any(w in question for w in self.deny_words)

    # ------------------------------------------------------------------
    # 匹配逻辑
    # ------------------------------------------------------------------
    def _match_entity(self, name: str, expected_type: str = "") -> list[tuple[str, str]]:
        """
        三级匹配：精确 → 子串 → 模糊。
        返回 [(canonical_name, entity_type), ...]
        """
        # Level 1: 精确匹配 — 优先在 expected_type 的词典中查
        if expected_type and expected_type in self.type_to_names:
            if name in self.type_to_names[expected_type]:
                return [(name, expected_type)]
        # 精确匹配 — 在所有词典中查
        if name in self.name_to_types:
            return [(name, t) for t in self.name_to_types[name]]

        # Level 2: 子串包含匹配
        results = self._substring_match(name, expected_type)
        if results:
            return results

        # Level 3: 模糊匹配
        results = self._fuzzy_match(name, expected_type)
        if results:
            return results

        return []

    def _substring_match(self, name: str, expected_type: str = "") -> list[tuple[str, str]]:
        """子串匹配：实体名包含词典词条 或 词典词条包含实体名。"""
        candidates = []
        # 优先搜索 expected_type
        search_types = ([expected_type] if expected_type in self.type_to_names else []) + \
                       [t for t in self.type_to_names if t != expected_type]

        for etype in search_types:
            for dict_name in self.type_to_names[etype]:
                if len(dict_name) < 2:
                    continue
                # 词典名 包含在 用户输入中，或 用户输入 包含在 词典名中
                if dict_name in name or name in dict_name:
                    # 优先选择更长的匹配（更精确）
                    candidates.append((dict_name, etype, len(dict_name)))
            if candidates:
                break  # 在第一个匹配到的类型中找到就停止

        if not candidates:
            return []
        # 取最长匹配
        candidates.sort(key=lambda x: x[2], reverse=True)
        best = candidates[0]
        return [(best[0], best[1])]

    def _fuzzy_match(self, name: str, expected_type: str = "") -> list[tuple[str, str]]:
        """模糊匹配：使用 rapidfuzz（或 difflib 降级）在词典中查找最接近的。"""
        best_name = ""
        best_type = ""
        best_score = 0.0

        # 优先搜索 expected_type
        search_types = ([expected_type] if expected_type in self.type_to_names else []) + \
                       [t for t in self.type_to_names if t != expected_type]

        for etype in search_types:
            for dict_name in self.type_to_names[etype]:
                score = self._similarity(name, dict_name)
                if score > best_score:
                    best_score = score
                    best_name = dict_name
                    best_type = etype
            # 如果在 expected_type 中找到足够好的匹配就停止
            if best_score >= self.threshold and etype == expected_type:
                break

        if best_score >= self.threshold:
            log.debug("模糊匹配 '%s' → '%s' (%s, score=%.1f)", name, best_name, best_type, best_score)
            return [(best_name, best_type)]
        return []

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """计算两个字符串的相似度（0-100）。"""
        if HAS_RAPIDFUZZ:
            return rf_fuzz.ratio(a, b)
        # 降级: difflib
        from difflib import SequenceMatcher
        return SequenceMatcher(None, a, b).ratio() * 100
