#!/usr/bin/env python3
# coding: utf-8
"""
上下文组装器：将检索到的子图转换为结构化文本，供 LLM 生成回答。
"""
from __future__ import annotations

import logging

from config import MAX_CONTEXT_CHARS, MAX_PROP_VALUE_LEN, MAX_TARGETS_PER_REL

log = logging.getLogger("graphrag")

# 关系类型中文标签
REL_LABELS: dict[str, str] = {
    "has_symptom": "症状",
    "acompany_with": "并发症",
    "common_drug": "常用药",
    "recommand_drug": "推荐药",
    "do_eat": "宜吃食物",
    "no_eat": "忌口食物",
    "recommand_eat": "推荐食谱",
    "need_check": "检查项目",
    "belongs_to": "所属科室",
    "drugs_of": "生产药品",
    "dept_belongs_to": "上级科室",
}

# 属性中文标签
PROP_LABELS: dict[str, str] = {
    "desc": "简介",
    "cause": "病因",
    "prevent": "预防措施",
    "cure_way": "治疗方式",
    "cure_lasttime": "治疗周期",
    "cured_prob": "治愈概率",
    "easy_get": "易感人群",
    "cost_money": "治疗费用",
}


class ContextBuilder:
    """将子图数据组装为结构化文本上下文。"""

    def build(self, subgraph: dict) -> dict:
        """
        组装上下文。

        返回:
          {
            "context_text": str,       # 完整上下文文本
            "context_preview": str,    # 前 500 字符（用于调试展示）
            "char_count": int,
          }
        """
        entities_found = subgraph.get("entities_found", [])
        nodes = {n["name"]: n for n in subgraph.get("nodes", [])}
        edges = subgraph.get("edges", [])

        # 按源节点分组边
        entity_edges: dict[str, list[dict]] = {}
        for edge in edges:
            entity_edges.setdefault(edge["source"], []).append(edge)
            # 反向也记录（因为查询是双向的）
            entity_edges.setdefault(edge["target"], []).append({
                "source": edge["target"], "source_label": edge["target_label"],
                "target": edge["source"], "target_label": edge["source_label"],
                "relationship": edge["relationship"],
            })

        sections: list[str] = []

        # 1. 优先展示查询实体
        for name in entities_found:
            node = nodes.get(name)
            if not node:
                continue
            section = self._build_entity_section(name, node, entity_edges.get(name, []))
            if section:
                sections.append(section)

        # 2. 展示 hop-1 中有属性的 Disease 节点
        for name, node in nodes.items():
            if name in entities_found:
                continue
            if node.get("label") == "Disease" and node.get("properties"):
                section = self._build_entity_section(name, node, entity_edges.get(name, []))
                if section:
                    sections.append(section)

        context_text = "\n\n".join(sections)

        # 截断
        if len(context_text) > MAX_CONTEXT_CHARS:
            context_text = context_text[:MAX_CONTEXT_CHARS] + "\n[...上下文已截断]"

        return {
            "context_text": context_text,
            "context_preview": context_text[:500],
            "char_count": len(context_text),
        }

    def _build_entity_section(self, name: str, node: dict,
                              edges: list[dict]) -> str:
        """构建单个实体的文本段落。"""
        label = node.get("label", "")
        lines = [f"【{label}】{name}"]

        # 属性
        props = node.get("properties", {})
        for key, value in props.items():
            if not value:
                continue
            prop_label = PROP_LABELS.get(key, key)
            if isinstance(value, list):
                val_str = "、".join(str(v) for v in value)
            else:
                val_str = str(value)
            if len(val_str) > MAX_PROP_VALUE_LEN:
                val_str = val_str[:MAX_PROP_VALUE_LEN] + "..."
            lines.append(f"  {prop_label}: {val_str}")

        # 关系（按类型分组）
        rel_groups: dict[str, list[str]] = {}
        for edge in edges:
            rel = edge.get("relationship", "")
            target = edge.get("target", "")
            if target and target != name:
                rel_groups.setdefault(rel, [])
                if target not in rel_groups[rel]:
                    rel_groups[rel].append(target)

        for rel, targets in rel_groups.items():
            rel_label = REL_LABELS.get(rel, rel)
            display = " / ".join(targets[:MAX_TARGETS_PER_REL])
            if len(targets) > MAX_TARGETS_PER_REL:
                display += f" ...共{len(targets)}项"
            lines.append(f"  {rel_label}: {display}")

        return "\n".join(lines) if len(lines) > 1 else ""
