"""Deterministic query planning for the MedPulse GraphRAG workflow."""
from __future__ import annotations

from dataclasses import asdict, dataclass


INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cause": ("原因", "病因", "成因", "为什么会", "怎么引起"),
    "complication": ("并发症", "并发", "伴随疾病"),
    "symptom": ("症状", "表现", "不舒服", "征兆"),
    "check": ("检查", "化验", "检测", "筛查", "查什么"),
    "drug": ("药", "用药", "服用", "胶囊", "片剂", "剂量", "吃多少"),
    "food": ("饮食", "忌口", "食物", "营养", "宜吃", "不能吃"),
    "department": ("科室", "挂号", "什么科", "哪个科"),
    "prevent": ("预防", "避免", "护理"),
    "treatment": ("治疗", "怎么治", "治疗方式", "治疗方法"),
    "duration": ("多久", "疗程", "治疗周期"),
    "cure_rate": ("治愈率", "能治好吗", "能不能治好"),
    "susceptible": ("易感", "容易得", "高发人群", "哪些人容易"),
    "cost": ("费用", "多少钱", "治疗成本", "花费"),
    "lifestyle": ("作息", "睡眠", "熬夜", "运动", "锻炼", "生活方式"),
}

INTENT_FIELDS: dict[str, list[str]] = {
    "cause": ["cause"],
    "complication": ["acompany_with"],
    "symptom": ["has_symptom"],
    "check": ["need_check"],
    "drug": ["common_drug", "recommand_drug"],
    "food": ["do_eat", "no_eat", "recommand_eat"],
    "department": ["belongs_to", "dept_belongs_to"],
    "prevent": ["prevent"],
    "treatment": ["cure_way"],
    "duration": ["cure_lasttime"],
    "cure_rate": ["cured_prob"],
    "susceptible": ["easy_get"],
    "cost": ["cost_money"],
    # Curated nutrition and exercise guidance is stored as preventive evidence.
    # Keeping this field explicit also prevents mixed food/lifestyle questions
    # from being routed to the conversation-memory-only fallback.
    "lifestyle": ["prevent"],
    "general": ["desc"],
}

INTENT_RELATIONS: dict[str, list[str]] = {
    intent: [field for field in fields if field not in {
        "desc", "cause", "prevent", "cure_way", "cure_lasttime",
        "cured_prob", "easy_get", "cost_money",
    }]
    for intent, fields in INTENT_FIELDS.items()
}

HIGH_RISK_KEYWORDS = (
    "剂量", "加量", "减量", "停药", "换药", "急救", "胸痛",
    "呼吸困难", "昏迷", "大出血", "自杀", "轻生",
)
DETAIL_KEYWORDS = ("详细", "全面", "具体", "展开", "深入")
BRIEF_KEYWORDS = ("简单", "简要", "一句话", "概括", "简短")
AMBIGUOUS_PRONOUNS = ("它", "这个病", "这种病", "该病", "这种情况")


@dataclass(frozen=True)
class QueryPlan:
    intent: str
    intents: list[str]
    requested_fields: list[str]
    relation_filters: list[str]
    detail_level: str
    needs_clarification: bool
    risk_level: str

    def to_dict(self) -> dict:
        return asdict(self)


class QuestionPlanner:
    """Turn a user question into a stable, inspectable retrieval plan."""

    def plan(
        self,
        question: str,
        *,
        has_memory_entities: bool = False,
    ) -> QueryPlan:
        question = question.strip()
        intents = [
            intent
            for intent, keywords in INTENT_KEYWORDS.items()
            if any(keyword in question for keyword in keywords)
        ]
        if not intents:
            intents = ["general"]

        requested_fields = self._merge(INTENT_FIELDS.get(intent, []) for intent in intents)
        relation_filters = self._merge(INTENT_RELATIONS.get(intent, []) for intent in intents)
        detail_level = (
            "detailed" if any(keyword in question for keyword in DETAIL_KEYWORDS)
            else "brief" if any(keyword in question for keyword in BRIEF_KEYWORDS)
            else "standard"
        )
        needs_clarification = (
            not has_memory_entities
            and any(pronoun in question for pronoun in AMBIGUOUS_PRONOUNS)
        )
        risk_level = (
            "high" if any(keyword in question for keyword in HIGH_RISK_KEYWORDS)
            else "medium" if any(intent in {"drug", "treatment", "cure_rate"} for intent in intents)
            else "low"
        )
        return QueryPlan(
            intent=intents[0],
            intents=intents,
            requested_fields=requested_fields,
            relation_filters=relation_filters,
            detail_level=detail_level,
            needs_clarification=needs_clarification,
            risk_level=risk_level,
        )

    @staticmethod
    def _merge(groups) -> list[str]:
        merged: list[str] = []
        for group in groups:
            for item in group:
                if item not in merged:
                    merged.append(item)
        return merged
