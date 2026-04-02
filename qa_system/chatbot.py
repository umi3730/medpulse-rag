#!/usr/bin/env python3
# coding: utf-8
"""
问答编排器：串联 LLM 分析 → 实体归一化 → Cypher 生成 → 图谱查询 → 答案格式化。

三级降级策略：
  Level 1: 全 LLM（意图 + 实体均由 LLM 提供）
  Level 2: LLM 实体 + 关键词意图（LLM 意图识别失败时）
  Level 3: 词典 NER + 关键词意图（Ollama 完全不可用时）
"""
from __future__ import annotations

import logging

from config import (
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    OLLAMA_MODEL, OLLAMA_BASE_URL,
    DEFAULT_ANSWER, INTENT_TYPES,
)
from llm_engine import LLMEngine
from entity_normalizer import EntityNormalizer
from cypher_generator import CypherGenerator
from graph_query import GraphQueryExecutor
from answer_formatter import AnswerFormatter

log = logging.getLogger("qa")


class ChatBot:
    """医药知识图谱智能问答编排器。"""

    def __init__(self, neo4j_uri: str = NEO4J_URI, neo4j_user: str = NEO4J_USER,
                 neo4j_password: str = NEO4J_PASSWORD,
                 ollama_model: str = OLLAMA_MODEL, ollama_url: str = OLLAMA_BASE_URL,
                 answer_mode: str = "template", debug: bool = False):
        self.debug = debug

        # 核心组件
        self.llm_engine = LLMEngine(model=ollama_model, base_url=ollama_url)
        self.normalizer = EntityNormalizer()
        self.cypher_gen = CypherGenerator()
        self.graph_query = GraphQueryExecutor(neo4j_uri, neo4j_user, neo4j_password)
        self.formatter = AnswerFormatter(
            mode=answer_mode,
            llm=self.llm_engine.llm if answer_mode == "llm" else None,
        )

        # Level 3 降级组件（懒加载）
        self._fallback_actree = None
        self._fallback_wdtype_dict = None
        self._fallback_keyword_lists = None

    # ==================================================================
    # 公共接口
    # ==================================================================
    def chat(self, question: str) -> str:
        """主入口：接收问题，返回回答字符串。"""
        return self.chat_detail(question)["answer"]

    def chat_detail(self, question: str) -> dict:
        """
        详细问答接口：返回回答 + 调试信息 + 图谱数据。

        返回格式:
          {
            "answer": str,
            "debug": {"level": int, "intents": [...], "entities": {...},
                      "cypher_queries": [...], "result_count": int},
            "graph_data": {"nodes": [...], "edges": [...]}
          }
        """
        question = question.strip()
        empty = {
            "answer": DEFAULT_ANSWER,
            "debug": {"level": 0, "intents": [], "entities": {},
                      "cypher_queries": [], "result_count": 0},
            "graph_data": {"nodes": [], "edges": []},
        }
        if not question:
            return empty

        # Step 1: 语义分析（意图 + 实体）
        intents, entity_dict, level = self._analyze(question)

        if self.debug:
            log.info("[DEBUG] 意图: %s | 实体: %s | Level: %d", intents, entity_dict, level)

        if not intents or not entity_dict:
            empty["debug"]["level"] = level
            return empty

        # Step 2: Cypher 查询生成
        query_groups = self.cypher_gen.generate(intents, entity_dict)
        cypher_queries = []
        for g in query_groups:
            for q in g["queries"]:
                cypher_queries.append({"cypher": q["cypher"], "params": q["params"]})
                if self.debug:
                    log.info("[DEBUG] Cypher: %s | 参数: %s", q["cypher"][:80], q["params"])

        if not query_groups:
            empty["debug"].update(level=level, intents=intents, entities=entity_dict,
                                  cypher_queries=cypher_queries)
            return empty

        # Step 3: 执行查询
        results = self.graph_query.execute(query_groups)
        result_count = sum(len(r["answers"]) for r in results)
        if self.debug:
            log.info("[DEBUG] 查询结果: %d 条", result_count)

        # Step 4: 格式化回答
        answer = self.formatter.format(results)

        # Step 5: 提取图谱数据（节点 + 边）
        graph_data = self._extract_graph_data(results)

        return {
            "answer": answer if answer else DEFAULT_ANSWER,
            "debug": {
                "level": level,
                "intents": intents,
                "entities": entity_dict,
                "cypher_queries": cypher_queries,
                "result_count": result_count,
            },
            "graph_data": graph_data,
        }

    # ==================================================================
    # 图谱数据提取（供前端可视化）
    # ==================================================================
    @staticmethod
    def _extract_graph_data(results: list[dict]) -> dict:
        """从查询结果中提取 nodes 和 edges，用于力导向图可视化。"""
        nodes_set: dict[str, str] = {}  # name → label
        edges: list[dict] = []

        # 节点标签映射
        label_map = {
            "disease_symptom": ("Disease", "Symptom"),
            "symptom_disease": ("Disease", "Symptom"),
            "disease_acompany": ("Disease", "Disease"),
            "disease_do_food": ("Disease", "Food"),
            "disease_not_food": ("Disease", "Food"),
            "disease_drug": ("Disease", "Drug"),
            "disease_check": ("Disease", "Check"),
            "check_disease": ("Disease", "Check"),
            "drug_disease": ("Disease", "Drug"),
            "food_do_disease": ("Disease", "Food"),
            "food_not_disease": ("Disease", "Food"),
        }

        for group in results:
            qt = group["question_type"]
            labels = label_map.get(qt)
            for row in group["answers"]:
                m_name = row.get("m.name")
                n_name = row.get("n.name")
                r_name = row.get("r.name")
                if m_name and n_name and labels:
                    nodes_set.setdefault(m_name, labels[0])
                    nodes_set.setdefault(n_name, labels[1])
                    edges.append({
                        "source": m_name, "target": n_name,
                        "label": r_name or qt,
                    })

        nodes = [{"id": name, "label": lbl} for name, lbl in nodes_set.items()]
        return {"nodes": nodes, "edges": edges}

    # ==================================================================
    # 语义分析（含降级）
    # ==================================================================
    def _analyze(self, question: str) -> tuple[list[str], dict[str, list[str]], int]:
        """分析问题，返回 (intents, entity_dict, level)。"""
        analysis = self.llm_engine.analyze(question)

        if analysis and analysis["entities"]:
            # 归一化实体
            normalized = self.normalizer.normalize(
                analysis["entities"], analysis["has_negation"]
            )
            entity_dict = normalized["entity_dict"]
            entities_map = normalized["entities"]

            if entity_dict:
                intents = analysis.get("intents", [])
                if intents:
                    # Level 1: 全 LLM — 意图和实体都有
                    if self.debug:
                        log.info("[DEBUG] Level 1: 全 LLM 模式")
                    return intents, entity_dict, 1
                else:
                    # Level 2: LLM 实体 + 关键词意图
                    if self.debug:
                        log.info("[DEBUG] Level 2: LLM 实体 + 关键词意图")
                    types = set()
                    for type_list in entities_map.values():
                        types.update(type_list)
                    intents = self._keyword_classify(question, types)
                    return intents, entity_dict, 2

        # Level 3: 词典 NER + 关键词意图
        if self.debug:
            log.info("[DEBUG] Level 3: 词典 NER + 关键词意图")
        intents, entity_dict = self._fallback_full(question)
        return intents, entity_dict, 3

    # ==================================================================
    # Level 3 降级：词典 NER + 关键词分类
    # ==================================================================
    def _fallback_full(self, question: str) -> tuple[list[str], dict[str, list[str]]]:
        """完全降级：AC 自动机 NER + 关键词意图识别。"""
        self._ensure_fallback_ready()

        # NER
        entities_map = self._fallback_ner(question)
        if not entities_map:
            return [], {}

        # 收集实体类型
        types = set()
        for type_list in entities_map.values():
            types.update(type_list)

        # 意图分类
        intents = self._keyword_classify(question, types)

        # 构建 entity_dict
        entity_dict: dict[str, list[str]] = {}
        for name, type_list in entities_map.items():
            for t in type_list:
                entity_dict.setdefault(t, [])
                if name not in entity_dict[t]:
                    entity_dict[t].append(name)

        return intents, entity_dict

    def _fallback_ner(self, question: str) -> dict[str, list[str]]:
        """AC 自动机扫描问句，返回 {实体名: [类型, ...]}。"""
        region_wds = []
        for i in self._fallback_actree.iter(question):
            wd = i[1][1]
            region_wds.append(wd)
        # 去除被更长词包含的短词
        stop_wds = set()
        for wd1 in region_wds:
            for wd2 in region_wds:
                if wd1 in wd2 and wd1 != wd2:
                    stop_wds.add(wd1)
        final_wds = [w for w in region_wds if w not in stop_wds]
        return {w: self._fallback_wdtype_dict.get(w, []) for w in final_wds if self._fallback_wdtype_dict.get(w)}

    def _ensure_fallback_ready(self):
        """懒加载 AC 自动机和关键词列表。"""
        if self._fallback_actree is not None:
            return
        try:
            import ahocorasick
        except ImportError:
            log.error("pyahocorasick 未安装，Level 3 降级不可用")
            self._fallback_actree = type("Dummy", (), {"iter": lambda s, q: iter([])})()
            self._fallback_wdtype_dict = {}
            self._fallback_keyword_lists = self._build_keyword_lists()
            return

        # 加载所有词典构建 wdtype_dict
        wdtype_dict: dict[str, list[str]] = {}
        all_words = set()
        for etype, names in self.normalizer.type_to_names.items():
            for name in names:
                wdtype_dict.setdefault(name, [])
                if etype not in wdtype_dict[name]:
                    wdtype_dict[name].append(etype)
                all_words.add(name)

        # 构建 AC 自动机
        actree = ahocorasick.Automaton()
        for idx, word in enumerate(all_words):
            actree.add_word(word, (idx, word))
        actree.make_automaton()

        self._fallback_actree = actree
        self._fallback_wdtype_dict = wdtype_dict
        self._fallback_keyword_lists = self._build_keyword_lists()
        log.info("Level 3 降级组件初始化完成（AC 自动机: %d 词条）", len(all_words))

    # ==================================================================
    # 关键词意图分类（移植自 question_classifier.py）
    # ==================================================================
    def _keyword_classify(self, question: str, entity_types: set[str]) -> list[str]:
        """基于关键词匹配的意图分类。"""
        if self._fallback_keyword_lists is None:
            self._fallback_keyword_lists = self._build_keyword_lists()
        kw = self._fallback_keyword_lists
        question_types = []

        has_deny = any(w in question for w in self.normalizer.deny_words)

        if self._check_words(kw["symptom"], question) and "disease" in entity_types:
            question_types.append("disease_symptom")
        if self._check_words(kw["symptom"], question) and "symptom" in entity_types:
            question_types.append("symptom_disease")
        if self._check_words(kw["cause"], question) and "disease" in entity_types:
            question_types.append("disease_cause")
        if self._check_words(kw["acompany"], question) and "disease" in entity_types:
            question_types.append("disease_acompany")
        if self._check_words(kw["food"], question) and "disease" in entity_types:
            question_types.append("disease_not_food" if has_deny else "disease_do_food")
        if self._check_words(kw["food"] + kw["cure"], question) and "food" in entity_types:
            question_types.append("food_not_disease" if has_deny else "food_do_disease")
        if self._check_words(kw["drug"], question) and "disease" in entity_types:
            question_types.append("disease_drug")
        if self._check_words(kw["cure"], question) and "drug" in entity_types:
            question_types.append("drug_disease")
        if self._check_words(kw["check"], question) and "disease" in entity_types:
            question_types.append("disease_check")
        if self._check_words(kw["check"] + kw["cure"], question) and "check" in entity_types:
            question_types.append("check_disease")
        if self._check_words(kw["prevent"], question) and "disease" in entity_types:
            question_types.append("disease_prevent")
        if self._check_words(kw["lasttime"], question) and "disease" in entity_types:
            question_types.append("disease_lasttime")
        if self._check_words(kw["cureway"], question) and "disease" in entity_types:
            question_types.append("disease_cureway")
        if self._check_words(kw["cureprob"], question) and "disease" in entity_types:
            question_types.append("disease_cureprob")
        if self._check_words(kw["easyget"], question) and "disease" in entity_types:
            question_types.append("disease_easyget")

        # 默认：有疾病实体但没匹配到意图 → 返回描述
        if not question_types and "disease" in entity_types:
            question_types = ["disease_desc"]
        if not question_types and "symptom" in entity_types:
            question_types = ["symptom_disease"]

        return question_types

    @staticmethod
    def _build_keyword_lists() -> dict[str, list[str]]:
        """构建关键词列表（移植自 question_classifier.py）。"""
        return {
            "symptom": ["症状", "表征", "现象", "症候", "表现"],
            "cause": ["原因", "成因", "为什么", "怎么会", "怎样才", "咋样才", "怎样会",
                       "如何会", "为啥", "为何", "如何才会", "怎么才会", "会导致", "会造成"],
            "acompany": ["并发症", "并发", "一起发生", "一并发生", "一起出现", "一并出现",
                          "一同发生", "一同出现", "伴随发生", "伴随", "共现"],
            "food": ["饮食", "饮用", "吃", "食", "伙食", "膳食", "喝", "菜", "忌口",
                      "补品", "保健品", "食谱", "菜谱", "食用", "食物", "补品"],
            "drug": ["药", "药品", "用药", "胶囊", "口服液", "炎片"],
            "prevent": ["预防", "防范", "抵制", "抵御", "防止", "躲避", "逃避", "避开",
                         "免得", "逃开", "避掉", "躲开", "躲掉", "绕开",
                         "怎样才能不", "怎么才能不", "咋样才能不", "咋才能不", "如何才能不",
                         "怎样才不", "怎么才不", "咋样才不", "咋才不", "如何才不",
                         "怎样才可以不", "怎么才可以不", "咋样才可以不", "咋才可以不", "如何可以不",
                         "怎样才可不", "怎么才可不", "咋样才可不", "咋才可不", "如何可不"],
            "lasttime": ["周期", "多久", "多长时间", "多少时间", "几天", "几年",
                          "多少天", "多少小时", "几个小时", "多少年"],
            "cureway": ["怎么治疗", "如何医治", "怎么医治", "怎么治", "怎么医",
                         "如何治", "医治方式", "疗法", "咋治", "怎么办", "咋办"],
            "cureprob": ["多大概率能治好", "多大几率能治好", "治好希望大么", "几率",
                          "几成", "比例", "可能性", "能治", "可治", "可以治", "可以医"],
            "easyget": ["易感人群", "容易感染", "易发人群", "什么人", "哪些人",
                         "感染", "染上", "得上"],
            "check": ["检查", "检查项目", "查出", "测出", "试出"],
            "cure": ["治疗什么", "治啥", "治疗啥", "医治啥", "治愈啥", "主治啥",
                      "主治什么", "有什么用", "有何用", "用处", "用途", "有什么好处",
                      "有什么益处", "有何益处", "用来", "用来做啥", "用来作甚", "需要", "要"],
        }

    @staticmethod
    def _check_words(words: list[str], sent: str) -> bool:
        return any(w in sent for w in words)
