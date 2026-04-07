#!/usr/bin/env python3
# coding: utf-8
"""
医药知识图谱数据爬虫 — CLI 入口

用法:
    python3 main.py                          # 爬取全部 1-11000
    python3 main.py --start 1 --end 100      # 指定范围
    python3 main.py --resume                  # 断点续爬
    python3 main.py --start 1 --end 5 --test  # 测试模式，打印不写文件
"""

import argparse
import logging

from config import OUTPUT_PATH
from spider import MedicalSpider

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)


def main():
    parser = argparse.ArgumentParser(description="医药知识图谱数据爬虫")
    parser.add_argument("--start", type=int, default=1, help="起始页码 (默认 1)")
    parser.add_argument("--end", type=int, default=11000, help="结束页码 (默认 11000)")
    parser.add_argument("--output", type=str, default=str(OUTPUT_PATH), help="输出文件路径")
    parser.add_argument("--resume", action="store_true", help="断点续爬")
    parser.add_argument("--delay", type=float, default=0.3, help="请求间隔秒数 (默认 0.3)")
    parser.add_argument("--test", action="store_true", help="测试模式：只打印不写文件")
    parser.add_argument("--ollama-model", type=str, default="qwen3:8b", help="Ollama 模型名 (默认 qwen3:8b)")
    parser.add_argument("--ollama-url", type=str, default="http://localhost:11434", help="Ollama 服务地址")
    args = parser.parse_args()

    spider = MedicalSpider(
        output_path=args.output,
        start_page=args.start,
        end_page=args.end,
        delay=args.delay,
        test_mode=args.test,
        ollama_model=args.ollama_model,
        ollama_url=args.ollama_url,
    )
    spider.crawl(resume=args.resume)


if __name__ == "__main__":
    main()
