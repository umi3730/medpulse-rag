#!/usr/bin/env python3
# coding: utf-8
"""
知识图谱配置：Schema 定义（节点/关系/属性）。
共享设置（Neo4j、路径）从 settings.py 导入。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from settings import (  # noqa: E402, F401
    PROJECT_DIR, DATA_DIR,
    NEO4J_URI, NEO4J_USER, NEO4J_DATABASE, NEO4J_PASSWORD,
)
from evidence_metadata import (  # noqa: E402, F401
    DEFAULT_EVIDENCE_LEVEL,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_URL,
    DEFAULT_UPDATED_AT,
)

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = DATA_DIR / "medical.json"

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

EVIDENCE_PROPS = [
    "source_name", "source_url", "updated_at", "evidence_level",
]
