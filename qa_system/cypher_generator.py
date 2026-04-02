#!/usr/bin/env python3
# coding: utf-8
"""
Cypher 查询生成器：将意图 + 实体转换为参数化 Cypher 查询。

使用模板方式（非 LLM），确保可靠性和安全性。
所有查询使用 $name 参数绑定，防止注入。
"""
from __future__ import annotations

import logging

from config import INTENT_TYPES

log = logging.getLogger("qa")

# ---------------------------------------------------------------------------
# 18 种意图对应的 Cypher 查询模板
# ---------------------------------------------------------------------------
CYPHER_TEMPLATES: dict[str, list[str]] = {
    # 疾病 → 症状
    "disease_symptom": [
        "MATCH (m:Disease)-[r:has_symptom]->(n:Symptom) WHERE m.name = $name RETURN m.name, r.name, n.name",
    ],
    # 症状 → 疾病
    "symptom_disease": [
        "MATCH (m:Disease)-[r:has_symptom]->(n:Symptom) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 病因
    "disease_cause": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.cause",
    ],
    # 疾病 → 并发症（双向）
    "disease_acompany": [
        "MATCH (m:Disease)-[r:acompany_with]->(n:Disease) WHERE m.name = $name RETURN m.name, r.name, n.name",
        "MATCH (m:Disease)-[r:acompany_with]->(n:Disease) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 宜吃食物
    "disease_do_food": [
        "MATCH (m:Disease)-[r:do_eat]->(n:Food) WHERE m.name = $name RETURN m.name, r.name, n.name",
        "MATCH (m:Disease)-[r:recommand_eat]->(n:Food) WHERE m.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 忌口食物
    "disease_not_food": [
        "MATCH (m:Disease)-[r:no_eat]->(n:Food) WHERE m.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 药品
    "disease_drug": [
        "MATCH (m:Disease)-[r:common_drug]->(n:Drug) WHERE m.name = $name RETURN m.name, r.name, n.name",
        "MATCH (m:Disease)-[r:recommand_drug]->(n:Drug) WHERE m.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 检查
    "disease_check": [
        "MATCH (m:Disease)-[r:need_check]->(n:Check) WHERE m.name = $name RETURN m.name, r.name, n.name",
    ],
    # 疾病 → 预防
    "disease_prevent": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.prevent",
    ],
    # 疾病 → 治疗周期
    "disease_lasttime": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.cure_lasttime",
    ],
    # 疾病 → 治疗方式
    "disease_cureway": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.cure_way",
    ],
    # 疾病 → 治愈概率
    "disease_cureprob": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.cured_prob",
    ],
    # 疾病 → 易感人群
    "disease_easyget": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.easy_get",
    ],
    # 疾病 → 描述
    "disease_desc": [
        "MATCH (m:Disease) WHERE m.name = $name RETURN m.name, m.desc",
    ],
    # 检查 → 疾病
    "check_disease": [
        "MATCH (m:Disease)-[r:need_check]->(n:Check) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
    # 药品 → 疾病
    "drug_disease": [
        "MATCH (m:Disease)-[r:common_drug]->(n:Drug) WHERE n.name = $name RETURN m.name, r.name, n.name",
        "MATCH (m:Disease)-[r:recommand_drug]->(n:Drug) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
    # 食物 → 疾病（有益）
    "food_do_disease": [
        "MATCH (m:Disease)-[r:do_eat]->(n:Food) WHERE n.name = $name RETURN m.name, r.name, n.name",
        "MATCH (m:Disease)-[r:recommand_eat]->(n:Food) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
    # 食物 → 疾病（有害）
    "food_not_disease": [
        "MATCH (m:Disease)-[r:no_eat]->(n:Food) WHERE n.name = $name RETURN m.name, r.name, n.name",
    ],
}


class CypherGenerator:
    """将意图 + 实体字典转换为参数化 Cypher 查询组。"""

    def generate(self, intents: list[str], entity_dict: dict[str, list[str]]) -> list[dict]:
        """
        输入:
          intents: ["disease_symptom", ...]
          entity_dict: {"disease": ["糖尿病"], "symptom": ["头痛"], ...}

        输出: [
          {
            "question_type": "disease_symptom",
            "queries": [
              {"cypher": "MATCH ...", "params": {"name": "糖尿病"}}
            ]
          }
        ]
        """
        results = []
        for intent in intents:
            if intent not in CYPHER_TEMPLATES:
                log.warning("未知意图类型: %s", intent)
                continue

            # 确定该意图需要哪种实体
            intent_info = INTENT_TYPES.get(intent, {})
            entity_type = intent_info.get("entity_type", "disease")
            entities = entity_dict.get(entity_type, [])

            if not entities:
                log.debug("意图 %s 未找到 %s 类型实体", intent, entity_type)
                continue

            templates = CYPHER_TEMPLATES[intent]
            queries = []
            for entity_name in entities:
                for tmpl in templates:
                    queries.append({
                        "cypher": tmpl,
                        "params": {"name": entity_name},
                    })

            if queries:
                results.append({
                    "question_type": intent,
                    "queries": queries,
                })

        return results
