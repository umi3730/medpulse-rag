#!/usr/bin/env python3
# coding: utf-8
"""
医药知识图谱智能问答系统 — CLI 入口

用法:
    python3 main.py                                    # 交互式问答
    python3 main.py --question "糖尿病有什么症状"        # 单次问答
    python3 main.py --answer-mode llm                  # LLM 润色回答
    python3 main.py --debug                            # 显示调试信息
"""
from __future__ import annotations

import argparse
import logging
import sys

from config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, OLLAMA_MODEL, OLLAMA_BASE_URL
from chatbot import ChatBot


def main():
    parser = argparse.ArgumentParser(
        description="医药知识图谱智能问答系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
示例:
  python3 main.py                                    # 交互式问答
  python3 main.py --question "糖尿病有什么症状"        # 单次问答
  python3 main.py --answer-mode llm                  # LLM 润色回答
  python3 main.py --uri bolt://192.168.1.10:7687     # 远程 Neo4j
  python3 main.py --debug                            # 显示调试信息
""",
    )
    parser.add_argument("--uri", type=str, default=NEO4J_URI, help="Neo4j URI")
    parser.add_argument("--user", type=str, default=NEO4J_USER, help="Neo4j 用户名")
    parser.add_argument("--password", type=str, default=NEO4J_PASSWORD, help="Neo4j 密码")
    parser.add_argument("--ollama-model", type=str, default=OLLAMA_MODEL, help="Ollama 模型名称")
    parser.add_argument("--ollama-url", type=str, default=OLLAMA_BASE_URL, help="Ollama 服务地址")
    parser.add_argument("--answer-mode", choices=["template", "llm"], default="template",
                        help="回答模式：template（默认）或 llm（LLM 润色）")
    parser.add_argument("--question", "-q", type=str, default=None, help="单次问答模式")
    parser.add_argument("--debug", action="store_true", help="显示调试信息")
    args = parser.parse_args()

    # 日志配置
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 初始化
    print("正在初始化问答系统...")
    bot = ChatBot(
        neo4j_uri=args.uri,
        neo4j_user=args.user,
        neo4j_password=args.password,
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
        answer_mode=args.answer_mode,
        debug=args.debug,
    )
    print("初始化完成！\n")

    # 单次问答模式
    if args.question:
        answer = bot.chat(args.question)
        print(answer)
        return

    # 交互式模式
    print("医药智能问答系统（输入 quit/exit/q 退出）")
    print("=" * 50)
    while True:
        try:
            question = input("\n用户: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break
        if question.lower() in ("quit", "exit", "q"):
            print("再见！")
            break
        if not question:
            continue
        answer = bot.chat(question)
        print("助理:", answer)


if __name__ == "__main__":
    main()
