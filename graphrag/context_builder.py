#!/usr/bin/env python3
# coding: utf-8
"""
上下文组装器：将检索到的子图转换为结构化文本，供 LLM 生成回答。
"""
from __future__ import annotations

import logging

from .config import MAX_CONTEXT_CHARS, MAX_PROP_VALUE_LEN, MAX_TARGETS_PER_REL

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
        evidence_claims = subgraph.get("evidence_claims", [])
        claims_by_entity: dict[str, list[dict]] = {}
        for claim in evidence_claims:
            claims_by_entity.setdefault(claim.get("disease", ""), []).append(claim)

        # 按源节点分组边
        entity_edges: dict[str, list[dict]] = {}
        for edge in edges:
            entity_edges.setdefault(edge["source"], []).append(edge)
            # 反向也记录（因为查询是双向的）
            entity_edges.setdefault(edge["target"], []).append({
                "source": edge["target"], "source_label": edge["target_label"],
                "target": edge["source"], "target_label": edge["source_label"],
                "relationship": edge["relationship"],
                "evidence": edge.get("evidence", {}),
            })

        evidence_items = self._build_evidence_items(nodes, edges, evidence_claims)
        citation_map = self._build_citation_map(evidence_items)
        sections: list[str] = []

        # 1. 优先展示查询实体
        for name in entities_found:
            node = nodes.get(name)
            if not node:
                continue
            section = self._build_entity_section(
                name, node, entity_edges.get(name, []), citation_map,
                claims_by_entity.get(name, []),
            )
            if section:
                sections.append(section)

        # 2. 展示 hop-1 中有属性的 Disease 节点
        for name, node in nodes.items():
            if name in entities_found:
                continue
            if node.get("label") == "Disease" and node.get("properties"):
                section = self._build_entity_section(
                    name, node, entity_edges.get(name, []), citation_map,
                    claims_by_entity.get(name, []),
                )
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
            "evidence_items": evidence_items,
        }

    def _build_entity_section(
        self,
        name: str,
        node: dict,
        edges: list[dict],
        citation_map: dict[tuple[str, str, str, str], int],
        curated_claims: list[dict] | None = None,
    ) -> str:
        """构建单个实体的文本段落。"""
        label = node.get("label", "")
        lines = [f"【{label}】{name}"]

        # 属性
        curated_claims = curated_claims or []
        curated_predicates = {claim.get("predicate") for claim in curated_claims}
        for claim in curated_claims:
            value = str(claim.get("claim", ""))
            citation = citation_map.get(("claim", name, claim.get("predicate", ""), value))
            prop_label = PROP_LABELS.get(claim.get("predicate", ""), claim.get("predicate", ""))
            suffix = f" [{citation}]" if citation else ""
            lines.append(f"  {prop_label}: {value}{suffix}")

        props = node.get("properties", {})
        for key, value in props.items():
            if not value or key in curated_predicates:
                continue
            prop_label = PROP_LABELS.get(key, key)
            if isinstance(value, list):
                val_str = "、".join(str(v) for v in value)
            else:
                val_str = str(value)
            if len(val_str) > MAX_PROP_VALUE_LEN:
                val_str = val_str[:MAX_PROP_VALUE_LEN] + "..."
            citation = citation_map.get(("property", name, key, str(value)[:500]))
            suffix = f" [{citation}]" if citation else ""
            lines.append(f"  {prop_label}: {val_str}{suffix}")

        evidence = node.get("evidence", {})
        if evidence and props:
            lines.append(
                "  证据元数据: "
                f"来源={evidence.get('source_name', 'unknown')} | "
                f"更新={evidence.get('updated_at', 'unknown')} | "
                f"等级={evidence.get('evidence_level', 'unknown')}"
            )

        # 关系（按类型分组）
        rel_groups: dict[str, list[tuple[str, int | None]]] = {}
        for edge in edges:
            rel = edge.get("relationship", "")
            target = edge.get("target", "")
            if target and target != name:
                rel_groups.setdefault(rel, [])
                citation = citation_map.get(("relation", name, rel, target))
                if citation is None:
                    citation = citation_map.get(("relation", target, rel, name))
                if target not in {item[0] for item in rel_groups[rel]}:
                    rel_groups[rel].append((target, citation))

        for rel, targets in rel_groups.items():
            rel_label = REL_LABELS.get(rel, rel)
            display = " / ".join(
                f"{target} [{citation}]" if citation else target
                for target, citation in targets[:MAX_TARGETS_PER_REL]
            )
            if len(targets) > MAX_TARGETS_PER_REL:
                display += f" ...共{len(targets)}项"
            lines.append(f"  {rel_label}: {display}")

        return "\n".join(lines) if len(lines) > 1 else ""

    @staticmethod
    def _build_evidence_items(
        nodes: dict[str, dict], edges: list[dict], evidence_claims: list[dict] | None = None
    ) -> list[dict]:
        items: list[dict] = []
        seen: set[str] = set()
        relation_counts: dict[tuple[str, str], int] = {}
        curated_predicates: set[tuple[str, str]] = set()
        for claim in evidence_claims or []:
            evidence_id = str(claim.get("evidence_id", ""))
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            subject = str(claim.get("disease", ""))
            predicate = str(claim.get("predicate", ""))
            curated_predicates.add((subject, predicate))
            items.append({
                "id": evidence_id,
                "kind": "claim",
                "subject": subject,
                "predicate": predicate,
                "object": str(claim.get("claim", "")),
                **{key: value for key, value in claim.items() if key not in {
                    "evidence_id", "disease", "predicate", "claim"
                }},
            })
        for name, node in nodes.items():
            metadata = node.get("evidence", {})
            for field, value in node.get("properties", {}).items():
                if not value or (name, field) in curated_predicates:
                    continue
                evidence_id = f"property:{node.get('label', 'Node')}:{name}:{field}"
                if evidence_id in seen:
                    continue
                seen.add(evidence_id)
                items.append({
                    "id": evidence_id,
                    "kind": "property",
                    "subject": name,
                    "predicate": field,
                    "object": str(value)[:500],
                    **metadata,
                })

        for edge in edges:
            group = (edge.get("source", ""), edge.get("relationship", ""))
            if relation_counts.get(group, 0) >= MAX_TARGETS_PER_REL:
                continue
            evidence_id = (
                f"relation:{edge.get('source', '')}:"
                f"{edge.get('relationship', '')}:{edge.get('target', '')}"
            )
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            relation_counts[group] = relation_counts.get(group, 0) + 1
            items.append({
                "id": evidence_id,
                "kind": "relation",
                "subject": edge.get("source", ""),
                "predicate": edge.get("relationship", ""),
                "object": edge.get("target", ""),
                **edge.get("evidence", {}),
            })
        for index, item in enumerate(items, start=1):
            item["citation_index"] = index
        return items

    @staticmethod
    def _build_citation_map(
        evidence_items: list[dict],
    ) -> dict[tuple[str, str, str, str], int]:
        return {
            (
                str(item.get("kind", "")),
                str(item.get("subject", "")),
                str(item.get("predicate", "")),
                str(item.get("object", "")),
            ): int(item["citation_index"])
            for item in evidence_items
        }
