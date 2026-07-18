#!/usr/bin/env python3
# coding: utf-8
"""
知脉 MedPulse 统一配置

所有共享设置（Neo4j、LLM、路径等）的唯一来源。
通过环境变量或 .env 文件配置，模块特有配置保留在各模块的 config.py 中。
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# 加载 .env（python-dotenv 可选，未安装时跳过）
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 项目路径
# ---------------------------------------------------------------------------
PROJECT_DIR = Path(__file__).resolve().parent
DICT_DIR = PROJECT_DIR / "dict"
DATA_DIR = PROJECT_DIR / "data"
HF_HOME = Path(os.environ.get("HF_HOME", str(DATA_DIR / "huggingface")))
os.environ.setdefault("HF_HOME", str(HF_HOME))

EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "sentence_transformers")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
EMBEDDING_DEVICE = os.environ.get("EMBEDDING_DEVICE", "cpu")
EMBEDDING_LOCAL_FILES_ONLY = os.environ.get(
    "EMBEDDING_LOCAL_FILES_ONLY", "true"
).lower() in {"1", "true", "yes", "on"}
EMBEDDING_QUERY_PREFIX = os.environ.get(
    "EMBEDDING_QUERY_PREFIX",
    "为这个句子生成表示以用于检索相关文章：",
)
EMBEDDING_CACHE_DIR = Path(os.environ.get("EMBEDDING_CACHE_DIR", str(HF_HOME)))

# ---------------------------------------------------------------------------
# Neo4j
# ---------------------------------------------------------------------------
def _normalize_neo4j_uri(uri: str) -> str:
    """Keep a single place for future Neo4j URI compatibility tweaks."""
    return uri


NEO4J_URI = _normalize_neo4j_uri(os.environ.get("NEO4J_URI", "bolt://127.0.0.1:7687"))
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")

# ---------------------------------------------------------------------------
# LLM 配置
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama")  # ollama | openai | anthropic
LLM_MODEL = os.environ.get("LLM_MODEL", "qwen3:8b")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434")
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0"))
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "512"))
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "8"))
LLM_MAX_RETRIES = int(os.environ.get("LLM_MAX_RETRIES", "0"))

# 商业 API 密钥（仅 openai / anthropic 时需要）
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ---------------------------------------------------------------------------
# 实体词典路径
# ---------------------------------------------------------------------------
ENTITY_DICTS: dict[str, Path] = {
    "disease":    DICT_DIR / "disease.txt",
    "symptom":    DICT_DIR / "symptom.txt",
    "drug":       DICT_DIR / "drug.txt",
    "check":      DICT_DIR / "check.txt",
    "food":       DICT_DIR / "food.txt",
    "producer":   DICT_DIR / "producer.txt",
    "department": DICT_DIR / "department.txt",
}
DENY_DICT_PATH = DICT_DIR / "deny.txt"

# 模糊匹配阈值（0-100，rapidfuzz ratio 分数）
FUZZY_MATCH_THRESHOLD = int(os.environ.get("FUZZY_MATCH_THRESHOLD", "80"))

# ---------------------------------------------------------------------------
# 通用回答设置
# ---------------------------------------------------------------------------
ANSWER_NUM_LIMIT = 20
DEFAULT_ANSWER = "现有资料不足以可靠回答这个问题，请补充具体疾病名称或换一种问法。"


# ---------------------------------------------------------------------------
# LLM 工厂函数
# ---------------------------------------------------------------------------
def create_llm(
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    **kwargs,
):
    """
    创建 LangChain BaseChatModel 实例。

    参数优先级: 函数参数 > 环境变量 > 默认值。
    依赖包未安装时返回 None。
    """
    _provider = provider or LLM_PROVIDER
    _model = model or LLM_MODEL
    _base_url = base_url or LLM_BASE_URL
    _temp = temperature if temperature is not None else LLM_TEMPERATURE
    _max_tokens = max_tokens or LLM_MAX_TOKENS
    _timeout = float(kwargs.pop("timeout", LLM_TIMEOUT))
    _max_retries = int(kwargs.pop("max_retries", LLM_MAX_RETRIES))

    if _provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=_model,
                base_url=_base_url,
                temperature=_temp,
                num_predict=_max_tokens,
                **kwargs,
            )
        except ImportError:
            return None

    elif _provider == "openai":
        try:
            import httpx
            from langchain_openai import ChatOpenAI
            api_key = kwargs.pop("api_key", None) or OPENAI_API_KEY
            oai_base = kwargs.pop("openai_base_url", None) or OPENAI_BASE_URL or None
            return ChatOpenAI(
                model=_model,
                api_key=api_key,
                base_url=oai_base,
                temperature=_temp,
                max_tokens=_max_tokens,
                timeout=_timeout,
                max_retries=_max_retries,
                http_client=httpx.Client(trust_env=False, timeout=_timeout),
                http_async_client=httpx.AsyncClient(trust_env=False, timeout=_timeout),
                **kwargs,
            )
        except ImportError:
            return None

    elif _provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            api_key = kwargs.pop("api_key", None) or ANTHROPIC_API_KEY
            return ChatAnthropic(
                model=_model,
                api_key=api_key,
                temperature=_temp,
                max_tokens=_max_tokens,
                **kwargs,
            )
        except ImportError:
            return None

    else:
        raise ValueError(f"不支持的 LLM 提供商: {_provider}。可选: ollama, openai, anthropic")
