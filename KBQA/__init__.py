"""
医药知识图谱智能问答系统

基于 LLM (LangChain + Ollama) 的意图识别和实体抽取，
结合 Neo4j 知识图谱的结构化问答。
"""
from .chatbot import ChatBot

__all__ = ["ChatBot"]
