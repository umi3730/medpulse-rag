#!/usr/bin/env python3
# coding: utf-8
"""
医药知识图谱构建入口

用法:
    python3 main.py                                         # 默认参数
    python3 main.py --uri bolt://192.168.1.10:7687          # 远程 Neo4j
    python3 main.py --data ../data/medical.json --clear     # 指定数据文件并清空旧图谱
    python3 main.py --step nodes                            # 只创建节点
    python3 main.py --step rels                             # 只创建关系
"""

import argparse
import logging
import sys
import time

from config import DATA_PATH, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NODE_LABELS
from data_loader import DataLoader
from graph_builder import GraphBuilder

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("kg")


def build_nodes(builder, nodes, disease_infos):
    """Step 1: 创建所有节点。"""
    log.info("========== Step 1: 创建节点 ==========")
    t0 = time.time()

    # 先创建疾病节点（带属性）
    builder.create_disease_nodes(disease_infos)

    # 再创建其他简单节点
    for label in ["Drug", "Food", "Check", "Department", "Producer", "Symptom"]:
        if nodes[label]:
            builder.create_simple_nodes(label, nodes[label])

    elapsed = time.time() - t0
    log.info("所有节点创建完成，耗时 %.1f 秒", elapsed)


def build_rels(builder, rels):
    """Step 2: 创建所有关系。"""
    log.info("========== Step 2: 创建关系 ==========")
    t0 = time.time()

    # 按顺序创建关系
    rel_order = [
        "has_symptom", "acompany_with", "belongs_to", "dept_belongs_to",
        "common_drug", "recommand_drug", "do_eat", "no_eat",
        "recommand_eat", "need_check", "drugs_of",
    ]
    for rel_type in rel_order:
        pairs = rels.get(rel_type, [])
        if pairs:
            builder.create_relationships(rel_type, pairs)

    elapsed = time.time() - t0
    log.info("所有关系创建完成，耗时 %.1f 秒", elapsed)


def main():
    parser = argparse.ArgumentParser(description="医药知识图谱构建工具")
    parser.add_argument("--uri", type=str, default=NEO4J_URI,
                        help=f"Neo4j 连接地址 (默认 {NEO4J_URI})")
    parser.add_argument("--user", type=str, default=NEO4J_USER,
                        help=f"Neo4j 用户名 (默认 {NEO4J_USER})")
    parser.add_argument("--password", type=str, default=NEO4J_PASSWORD,
                        help="Neo4j 密码")
    parser.add_argument("--data", type=str, default=str(DATA_PATH),
                        help="JSONL 数据文件路径")
    parser.add_argument("--clear", action="store_true",
                        help="构建前清空已有图谱数据")
    parser.add_argument("--step", choices=["all", "nodes", "rels"],
                        default="all", help="执行步骤: all / nodes / rels")
    args = parser.parse_args()

    # 1. 加载数据
    log.info("加载数据: %s", args.data)
    loader = DataLoader(args.data)
    nodes, rels, disease_infos = loader.load()

    # 2. 连接 Neo4j
    try:
        builder = GraphBuilder(args.uri, args.user, args.password)
    except Exception as e:
        log.error("无法连接 Neo4j: %s", e)
        sys.exit(1)

    # 3. 清空（可选）
    if args.clear:
        builder.clear_all()

    # 4. 创建索引
    builder.create_indexes(NODE_LABELS)

    # 5. 执行构建
    t_start = time.time()

    if args.step in ("all", "nodes"):
        build_nodes(builder, nodes, disease_infos)
    if args.step in ("all", "rels"):
        build_rels(builder, rels)

    total_time = time.time() - t_start
    log.info("========== 图谱构建完成，总耗时 %.1f 秒 ==========", total_time)


if __name__ == "__main__":
    main()
