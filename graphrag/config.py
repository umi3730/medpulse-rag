#!/usr/bin/env python3
# coding: utf-8
"""
GraphRAG 配置：检索/生成参数和提示词。
共享设置从 settings.py 导入。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# 从统一配置导入共享设置（re-export）
from settings import (  # noqa: E402, F401
    NEO4J_URI, NEO4J_USER, NEO4J_DATABASE, NEO4J_PASSWORD,
    LLM_MODEL, LLM_BASE_URL,
    LLM_TEMPERATURE, LLM_MAX_TOKENS,
    ENTITY_DICTS, DENY_DICT_PATH, FUZZY_MATCH_THRESHOLD,
    DEFAULT_ANSWER,
    create_llm,
)

# 向后兼容别名
OLLAMA_MODEL = LLM_MODEL
OLLAMA_BASE_URL = LLM_BASE_URL
LLM_NUM_PREDICT = LLM_MAX_TOKENS

# ---------------------------------------------------------------------------
# 子图检索参数
# ---------------------------------------------------------------------------
MAX_HOPS = 2               # 最大遍历深度
HOP1_LIMIT = 50            # 每个实体的 hop-1 邻居上限
HOP2_LIMIT = 20            # 每个 hop-1 节点的 hop-2 邻居上限
HOP2_CANDIDATES = 15       # hop-2 扩展的候选节点数上限

# Disease 节点需要获取的属性
DISEASE_PROPERTIES = [
    "desc", "cause", "prevent", "cure_way", "cure_lasttime",
    "cured_prob", "easy_get", "cost_money",
]

# ---------------------------------------------------------------------------
# 上下文组装
# ---------------------------------------------------------------------------
MAX_CONTEXT_CHARS = 6000    # 传给 LLM 的上下文最大字符数
MAX_PROP_VALUE_LEN = 200    # 单个属性值截断长度
MAX_TARGETS_PER_REL = 15    # 每种关系最多列出的目标数

# ---------------------------------------------------------------------------
# LLM 生成
# ---------------------------------------------------------------------------
LLM_NUM_PREDICT_GENERATION = 1024  # 生成回答的最大 token 数

# ---------------------------------------------------------------------------
# 实体抽取提示词（仅抽取实体，不分类意图）
# ---------------------------------------------------------------------------
ENTITY_EXTRACT_PROMPT = """\
你是医药知识图谱的实体提取器。从用户问题中提取所有医疗相关实体。

## 实体类型
- disease: 疾病名称（如：糖尿病、高血压、感冒）
- symptom: 症状表现（如：头痛、发烧、咳嗽）
- drug: 药品名称（如：阿莫西林、布洛芬）
- check: 检查项目（如：血常规、CT、心电图）
- food: 食物名称（如：苹果、牛奶、西红柿）
- department: 科室名称（如：内科、外科、儿科）

## 输出要求
严格输出以下 JSON 格式，不要输出任何其他内容：
{"entities": [{"name": "实体名", "type": "实体类型"}]}

注意：
1. 只提取实体，不需要识别意图
2. entities 必须是问句中明确提到的医疗实体
3. 如果无法识别为医疗问题，返回 {"entities": []}
/no_think"""

# ---------------------------------------------------------------------------
# 答案生成提示词
# ---------------------------------------------------------------------------
GENERATION_SYSTEM_PROMPT = """\
你是一个专业的医疗知识问答助手。根据提供的知识图谱数据回答用户的医疗问题。

## 回答要求
1. 严格基于提供的图谱数据回答，不要编造未提及的信息
2. 如果图谱数据不足以回答问题，明确说明"根据现有数据暂无相关信息"
3. 用自然流畅的中文回答，适当组织信息
4. 涉及多个实体时，分段说明各实体的相关信息
5. 在回答末尾注明"以上信息仅供参考，具体请咨询专业医生。"

## 知识图谱数据
{context}
/no_think"""
