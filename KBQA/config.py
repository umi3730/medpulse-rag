#!/usr/bin/env python3
# coding: utf-8
"""
问答系统配置：意图/实体定义、提示词。
共享设置（Neo4j、LLM、路径）从 settings.py 导入。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 从统一配置导入共享设置（re-export 供本模块内其他文件使用）
from settings import (  # noqa: E402, F401
    PROJECT_DIR, DICT_DIR, DATA_DIR,
    NEO4J_URI, NEO4J_USER, NEO4J_DATABASE, NEO4J_PASSWORD,
    LLM_PROVIDER, LLM_MODEL, LLM_BASE_URL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS,
    ENTITY_DICTS, DENY_DICT_PATH, FUZZY_MATCH_THRESHOLD,
    ANSWER_NUM_LIMIT, DEFAULT_ANSWER,
    create_llm,
)

# 向后兼容别名
OLLAMA_MODEL = LLM_MODEL
OLLAMA_BASE_URL = LLM_BASE_URL
LLM_NUM_PREDICT = LLM_MAX_TOKENS

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# 18 种意图类型
# ---------------------------------------------------------------------------
INTENT_TYPES = {
    "disease_symptom":  {"entity_type": "disease",  "desc": "查询疾病的症状"},
    "symptom_disease":  {"entity_type": "symptom",  "desc": "根据症状查疾病"},
    "disease_cause":    {"entity_type": "disease",  "desc": "查询疾病的病因"},
    "disease_acompany": {"entity_type": "disease",  "desc": "查询疾病的并发症"},
    "disease_do_food":  {"entity_type": "disease",  "desc": "查询疾病宜吃的食物"},
    "disease_not_food": {"entity_type": "disease",  "desc": "查询疾病忌口的食物"},
    "disease_drug":     {"entity_type": "disease",  "desc": "查询疾病的常用药品"},
    "disease_check":    {"entity_type": "disease",  "desc": "查询疾病需要做的检查"},
    "disease_prevent":  {"entity_type": "disease",  "desc": "查询疾病的预防方法"},
    "disease_lasttime": {"entity_type": "disease",  "desc": "查询疾病的治疗周期"},
    "disease_cureway":  {"entity_type": "disease",  "desc": "查询疾病的治疗方式"},
    "disease_cureprob": {"entity_type": "disease",  "desc": "查询疾病的治愈概率"},
    "disease_easyget":  {"entity_type": "disease",  "desc": "查询疾病的易感人群"},
    "disease_desc":     {"entity_type": "disease",  "desc": "查询疾病的基本介绍"},
    "check_disease":    {"entity_type": "check",    "desc": "根据检查项查疾病"},
    "drug_disease":     {"entity_type": "drug",     "desc": "根据药品查疾病"},
    "food_do_disease":  {"entity_type": "food",     "desc": "查询某食物对哪些疾病有益"},
    "food_not_disease": {"entity_type": "food",     "desc": "查询某食物对哪些疾病有害"},
}

# ---------------------------------------------------------------------------
# LLM System Prompt
# ---------------------------------------------------------------------------
LLM_SYSTEM_PROMPT = """\
你是医药知识图谱问答系统的语义分析器。分析用户的医疗问题，提取意图和实体。

## 实体类型
- disease: 疾病名称（如：糖尿病、高血压、感冒）
- symptom: 症状表现（如：头痛、发烧、咳嗽）
- drug: 药品名称（如：阿莫西林、布洛芬）
- check: 检查项目（如：血常规、CT、心电图）
- food: 食物名称（如：苹果、牛奶、西红柿）
- department: 科室名称（如：内科、外科、儿科）

## 意图类型
- disease_symptom: 询问某疾病有什么症状
- symptom_disease: 根据症状问可能是什么病
- disease_cause: 询问疾病的病因/原因
- disease_acompany: 询问疾病的并发症
- disease_do_food: 询问疾病宜吃什么（没有否定词时选此项）
- disease_not_food: 询问疾病忌口/不能吃什么（有否定词时选此项）
- disease_drug: 询问疾病用什么药
- disease_check: 询问疾病做什么检查
- disease_prevent: 询问如何预防疾病
- disease_lasttime: 询问疾病治疗周期/多久能好
- disease_cureway: 询问疾病怎么治疗
- disease_cureprob: 询问疾病治愈概率/能不能治好
- disease_easyget: 询问哪些人容易得某疾病
- disease_desc: 询问疾病的基本介绍/是什么
- check_disease: 根据检查项查可检出的疾病
- drug_disease: 根据药品查能治什么病
- food_do_disease: 询问某食物对什么疾病有益
- food_not_disease: 询问某食物对什么疾病不利

## 输出要求
严格输出以下 JSON 格式，不要输出任何其他内容：
{"intents": ["意图类型1"], "entities": [{"name": "实体名", "type": "实体类型"}], "has_negation": false}

注意：
1. intents 可以有多个（一个问题可能涉及多个意图）
2. entities 必须是问句中明确提到的医疗实体
3. has_negation 表示问句是否包含否定/禁止含义（不、别、忌、禁止、不能等）
4. 如果无法识别为医疗问题，返回 {"intents": [], "entities": [], "has_negation": false}
/no_think"""
