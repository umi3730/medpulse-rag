#!/usr/bin/env python3
# coding: utf-8
"""
数据加载器：读取 JSONL 文件，提取节点集合与关系列表。

输出结构:
  nodes   = {label: set(name, ...)}       7 类节点
  rels    = {rel_type: [(src, dst), ...]}  11 类关系
  disease_infos = [dict, ...]              疾病属性详情（用于创建 Disease 节点）
"""

import json
import logging
from pathlib import Path

from config import (
    DEFAULT_EVIDENCE_LEVEL,
    DEFAULT_SOURCE_NAME,
    DEFAULT_SOURCE_URL,
    DEFAULT_UPDATED_AT,
    DISEASE_PROPS,
)

log = logging.getLogger("kg")


class DataLoader:
    """从 JSONL 文件加载医疗数据，一次性提取全部节点和关系。"""

    def __init__(self, data_path):
        self.data_path = Path(data_path)

    def load(self):
        """
        返回 (nodes, rels, disease_infos)
          nodes:  dict[str, set]  — 键为节点标签，值为名称集合
          rels:   dict[str, list] — 键为关系类型，值为 (src, dst) 元组列表
          disease_infos: list[dict] — 每个疾病的属性字典
        """
        nodes = {
            "Drug": set(), "Food": set(), "Check": set(),
            "Department": set(), "Producer": set(), "Symptom": set(),
            "Disease": set(),
        }
        rels = {
            "has_symptom": [], "acompany_with": [], "belongs_to": [],
            "dept_belongs_to": [], "common_drug": [], "recommand_drug": [],
            "do_eat": [], "no_eat": [], "recommand_eat": [],
            "need_check": [], "drugs_of": [],
        }
        disease_infos = []

        count = 0
        for line in open(self.data_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            name = data.get("name", "").strip()
            if not name:
                continue

            count += 1
            nodes["Disease"].add(name)

            # ---- 疾病属性 ----
            info = {k: data.get(k, "") for k in DISEASE_PROPS}
            info["name"] = name
            info["source_name"] = data.get("source_name") or DEFAULT_SOURCE_NAME
            info["source_url"] = data.get("source_url") or DEFAULT_SOURCE_URL
            info["updated_at"] = data.get("updated_at") or DEFAULT_UPDATED_AT
            info["evidence_level"] = data.get("evidence_level") or DEFAULT_EVIDENCE_LEVEL
            # 列表字段转字符串存储
            for k in ("cure_department", "cure_way"):
                v = info.get(k, "")
                if isinstance(v, list):
                    info[k] = "，".join(v)
            disease_infos.append(info)

            # ---- 症状 ----
            for s in data.get("symptom", []):
                nodes["Symptom"].add(s)
                rels["has_symptom"].append((name, s))

            # ---- 并发症 ----
            for a in data.get("acompany", []):
                rels["acompany_with"].append((name, a))

            # ---- 科室（含层级关系）----
            dept = data.get("cure_department", [])
            if isinstance(dept, list):
                for d in dept:
                    nodes["Department"].add(d)
                if len(dept) == 1:
                    rels["belongs_to"].append((name, dept[0]))
                elif len(dept) >= 2:
                    big, small = dept[0], dept[1]
                    rels["dept_belongs_to"].append((small, big))
                    rels["belongs_to"].append((name, small))

            # ---- 常用药品 ----
            for d in data.get("common_drug", []):
                nodes["Drug"].add(d)
                rels["common_drug"].append((name, d))

            # ---- 推荐药品 ----
            for d in data.get("recommand_drug", []):
                nodes["Drug"].add(d)
                rels["recommand_drug"].append((name, d))

            # ---- 食物（宜吃/忌吃/推荐）----
            for f in data.get("do_eat", []):
                nodes["Food"].add(f)
                rels["do_eat"].append((name, f))
            for f in data.get("not_eat", []):
                nodes["Food"].add(f)
                rels["no_eat"].append((name, f))
            for f in data.get("recommand_eat", []):
                nodes["Food"].add(f)
                rels["recommand_eat"].append((name, f))

            # ---- 检查项 ----
            for c in data.get("check", []):
                nodes["Check"].add(c)
                rels["need_check"].append((name, c))

            # ---- 药品厂商 ----
            for detail in data.get("drug_detail", []):
                if "(" in detail:
                    producer = detail.split("(")[0]
                    drug_name = detail.split("(")[-1].replace(")", "")
                    if producer and drug_name:
                        nodes["Producer"].add(producer)
                        rels["drugs_of"].append((producer, drug_name))

        # 去重关系
        for key in rels:
            rels[key] = list(set(rels[key]))

        log.info("数据加载完成：%d 条疾病记录", count)
        for label, s in nodes.items():
            log.info("  节点 %-12s: %d", label, len(s))
        for rel_type, pairs in rels.items():
            log.info("  关系 %-16s: %d", rel_type, len(pairs))

        return nodes, rels, disease_infos
