from __future__ import annotations

import unittest

from graphrag.langgraph_flow import HAS_LANGGRAPH, LangGraphRAGFlow
from graphrag.graphrag_bot import GraphRAGBot
from graphrag.question_planner import QuestionPlanner


class FakeExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, question: str) -> list[dict]:
        self.calls += 1
        return [{"name": "糖尿病", "type": "disease"}]


class FakeNormalizer:
    def normalize(self, entities: list[dict], has_negation: bool = False) -> dict:
        return {"entity_dict": {"disease": ["糖尿病"]}}


class FakeRetriever:
    def __init__(self) -> None:
        self.kwargs: dict = {}

    def retrieve(self, entity_dict: dict, **kwargs) -> dict:
        self.kwargs = kwargs
        return {
            "entities_found": ["糖尿病"],
            "nodes": [{
                "name": "糖尿病",
                "label": "Disease",
                "properties": {"cause": "测试病因"},
            }],
            "edges": [],
            "stats": {"total_nodes": 1, "total_edges": 0},
        }


class FakeContextBuilder:
    def build(self, subgraph: dict) -> dict:
        return {
            "context_text": "糖尿病病因：测试病因",
            "context_preview": "糖尿病病因：测试病因",
            "char_count": 11,
        }


class FakeGenerator:
    def __init__(self) -> None:
        self.last_plan: dict | None = None
        self.last_context = ""
        self.last_conversation_context = ""

    def generate(
        self, question: str, context: str, query_plan: dict | None = None,
        conversation_context: str = "",
    ) -> dict:
        self.last_plan = query_plan
        self.last_context = context
        self.last_conversation_context = conversation_context
        return {"answer": "测试回答", "generation_time_ms": 1, "model_used": "fake"}

    def stream(
        self, question: str, context: str, query_plan: dict | None = None,
        conversation_context: str = "",
    ):
        self.last_plan = query_plan
        self.last_context = context
        self.last_conversation_context = conversation_context
        yield "测试回答"
        yield {"generation_time_ms": 1, "model_used": "fake"}


class FakeMemoryStore:
    def __init__(self, entities: dict | None = None, context_text: str = "") -> None:
        self.entities = entities or {}
        self.context_text = context_text
        self.turns: list[dict] = []

    def build_context(self, **kwargs) -> dict:
        return {
            "context_text": self.context_text,
            "entities": self.entities,
            "recent_turns": [],
        }

    def add_turn(self, **kwargs) -> None:
        self.turns.append(kwargs)


@unittest.skipUnless(HAS_LANGGRAPH, "langgraph is not installed")
class LangGraphQueryPlanTests(unittest.TestCase):
    def build_flow(self, memory_store: FakeMemoryStore | None = None):
        extractor = FakeExtractor()
        retriever = FakeRetriever()
        flow = LangGraphRAGFlow(
            extractor=extractor,
            normalizer=FakeNormalizer(),
            retriever=retriever,
            context_builder=FakeContextBuilder(),
            generator=FakeGenerator(),
            memory_store=memory_store or FakeMemoryStore(),
        )
        return flow, extractor, retriever

    def test_property_plan_controls_retriever(self) -> None:
        flow, _, retriever = self.build_flow()
        response = flow.run("糖尿病可能由哪些原因引起？")
        self.assertEqual(response["debug"]["intent"], "cause")
        self.assertEqual(response["debug"]["requested_fields"], ["cause"])
        self.assertEqual(retriever.kwargs["property_filters"], ["cause"])
        self.assertFalse(retriever.kwargs["include_neighbors"])
        self.assertEqual(flow.generator.last_plan["requested_fields"], ["cause"])

    def test_ambiguous_question_asks_for_clarification(self) -> None:
        flow, extractor, retriever = self.build_flow()
        response = flow.run("这个病怎么治疗？")
        self.assertTrue(response["debug"]["needs_clarification"])
        self.assertEqual(response["debug"]["retrieval_mode"], "clarification")
        self.assertIn("哪一种疾病", response["answer"])
        self.assertEqual(extractor.calls, 0)
        self.assertEqual(retriever.kwargs, {})

    def test_memory_entity_allows_pronoun_followup(self) -> None:
        memory = FakeMemoryStore({"disease": ["糖尿病"]})
        flow, extractor, _ = self.build_flow(memory)
        response = flow.run("它有哪些并发症？")
        self.assertFalse(response["debug"]["needs_clarification"])
        self.assertEqual(response["debug"]["intent"], "complication")
        self.assertEqual(extractor.calls, 1)

    def test_conversation_memory_is_separate_from_medical_evidence(self) -> None:
        memory = FakeMemoryStore(context_text="UNVERIFIED_OLD_ANSWER")
        flow, _, _ = self.build_flow(memory)
        flow.run("糖尿病可能由哪些原因引起？")
        self.assertNotIn("UNVERIFIED_OLD_ANSWER", flow.generator.last_context)
        self.assertIn("UNVERIFIED_OLD_ANSWER", flow.generator.last_conversation_context)


class StreamingQueryPlanTests(unittest.TestCase):
    def build_bot(self, memory_store: FakeMemoryStore | None = None):
        bot = GraphRAGBot.__new__(GraphRAGBot)
        bot.debug = False
        bot.planner = QuestionPlanner()
        bot.memory_store = memory_store or FakeMemoryStore()
        bot.vector_store = None
        bot.extractor = FakeExtractor()
        bot.normalizer = FakeNormalizer()
        bot.retriever = FakeRetriever()
        bot.context_builder = FakeContextBuilder()
        bot.generator = FakeGenerator()
        return bot

    def test_streaming_path_uses_query_plan(self) -> None:
        bot = self.build_bot()
        events = list(bot.chat_stream("糖尿病可能由哪些原因引起？"))
        retrieval = events[0]["data"]["debug"]
        self.assertEqual(retrieval["intent"], "cause")
        self.assertEqual(retrieval["requested_fields"], ["cause"])
        self.assertEqual(bot.retriever.kwargs["property_filters"], ["cause"])
        self.assertFalse(bot.retriever.kwargs["include_neighbors"])
        self.assertEqual(bot.generator.last_plan["requested_fields"], ["cause"])

    def test_streaming_path_can_ask_for_clarification(self) -> None:
        bot = self.build_bot()
        events = list(bot.chat_stream("这个病怎么治疗？"))
        self.assertEqual([event["event"] for event in events], ["retrieval", "delta", "done"])
        self.assertTrue(events[0]["data"]["debug"]["needs_clarification"])
        self.assertIn("哪一种疾病", events[-1]["data"]["answer"])
        self.assertEqual(bot.extractor.calls, 0)


if __name__ == "__main__":
    unittest.main()
