#!/usr/bin/env python3
# coding: utf-8
"""
Neo4j 连接配置 & 图谱 Schema 定义
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
DATA_PATH = PROJECT_DIR / "data" / "medical.json"

# ---------------------------------------------------------------------------
# Neo4j 默认连接参数
# ---------------------------------------------------------------------------
NEO4J_URI = "bolt://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "neo4j"

# ---------------------------------------------------------------------------
# 图谱 Schema：7 类节点
# ---------------------------------------------------------------------------
NODE_LABELS = [
    "Disease",      # 疾病（中心实体，带属性）
    "Drug",         # 药品
    "Food",         # 食物
    "Check",        # 检查项
    "Department",   # 科室
    "Producer",     # 药品厂商
    "Symptom",      # 症状
]

# ---------------------------------------------------------------------------
# 图谱 Schema：11 类关系
# ---------------------------------------------------------------------------
REL_TYPES = {
    "has_symptom":    ("Disease", "Symptom",    "症状"),
    "acompany_with":  ("Disease", "Disease",    "并发症"),
    "belongs_to":     ("Disease", "Department", "所属科室"),
    "dept_belongs_to":("Department","Department","属于"),
    "common_drug":    ("Disease", "Drug",       "常用药品"),
    "recommand_drug": ("Disease", "Drug",       "好评药品"),
    "do_eat":         ("Disease", "Food",       "宜吃"),
    "no_eat":         ("Disease", "Food",       "忌吃"),
    "recommand_eat":  ("Disease", "Food",       "推荐食谱"),
    "need_check":     ("Disease", "Check",      "诊断检查"),
    "drugs_of":       ("Producer","Drug",       "生产药品"),
}

# ---------------------------------------------------------------------------
# 疾病节点携带的属性字段
# ---------------------------------------------------------------------------
DISEASE_PROPS = [
    "name", "desc", "prevent", "cause", "easy_get",
    "cure_department", "cure_way", "cure_lasttime",
    "cured_prob", "get_prob", "yibao_status",
    "get_way", "cost_money",
]
