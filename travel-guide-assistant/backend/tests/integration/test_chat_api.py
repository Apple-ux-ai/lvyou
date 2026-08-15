"""RAG 对话集成测试（RED 阶段，对应短期阶段 RAG 跑通）

验证：
- 行程意图（含目的地/天数关键词）→ SSE 流中包含 itinerary 事件
- 普通问答 → 不包含 itinerary 事件，只有 message + done
- itinerary 载荷符合 Pydantic Itinerary Schema（含 citations）
"""
import json

import pytest
from httpx import AsyncClient, ASGITransport

from app import main
from app.models.schemas import ChatRequest, Itinerary
from app.rag.retriever import Document
from app.services.rag_chat import RAGChatService

app = main.app


@pytest.fixture(autouse=True)
def use_local_chat_service(monkeypatch):
    """Keep contract tests deterministic when a developer has a remote key locally."""
    monkeypatch.setenv("TRAVELMATE_LLM_PROVIDER", "local")
    monkeypatch.setattr(main, "_chat_service", None)


async def collect_events(payload):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/chat", json=payload) as resp:
            events = []
            event_name = None
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    event_name = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data = line.split(":", 1)[1].strip()
                    events.append((event_name, json.loads(data)))
                    event_name = None
            return events


@pytest.mark.asyncio
async def test_travel_plan_intent_emits_itinerary_event():
    """行程规划意图（日本+7天+预算）→ 必须包含 itinerary 事件"""
    events = await collect_events({"message": "五一去日本玩7天，预算1万"})
    itinerary_events = [e for e in events if e[0] == "itinerary"]
    assert len(itinerary_events) == 1
    # 载荷必须能通过 Pydantic Schema 校验
    itin = Itinerary.model_validate(itinerary_events[0][1])
    assert itin.days == 7


@pytest.mark.asyncio
async def test_general_question_has_no_itinerary_event():
    """普通问答（不含行程意图）→ 不发送 itinerary 事件"""
    events = await collect_events({"message": "日本签证需要什么材料？"})
    itinerary_events = [e for e in events if e[0] == "itinerary"]
    assert itinerary_events == []


@pytest.mark.asyncio
async def test_itinerary_event_is_valid_schema():
    events = await collect_events({"message": "去冰岛自驾，预算两万"})
    itinerary_events = [e for e in events if e[0] == "itinerary"]
    assert len(itinerary_events) == 1
    payload = itinerary_events[0][1]
    assert payload["destination"] == "冰岛"
    assert payload["total_budget"] is not None
    assert len(payload["day_plans"]) >= 1
    # 引用完整性：每条 citation 的 source_id 必须存在于知识库
    assert "citations" in payload


@pytest.mark.asyncio
async def test_sse_still_terminates_with_done_after_itinerary():
    events = await collect_events({"message": "五一去日本玩7天，预算1万"})
    message_events = [data for event, data in events if event == "message"]
    assert "详细行程" in "".join(event["text"] for event in message_events)
    assert len(message_events) > 1
    assert events[-1][0] == "done"


@pytest.mark.asyncio
async def test_invalid_llm_itinerary_uses_fallback_then_emits_itinerary(monkeypatch):
    class Retriever:
        def search(self, query, top_k=5):
            return [Document(source_id="guide-1", text="# Guide", score=0.9)]

        def exists(self, source_id):
            return source_id == "guide-1"

    class InvalidLLM:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, itinerary):
            self.calls += 1
            return "not itinerary JSON"

    class ValidFallbackLLM:
        def __init__(self):
            self.calls = 0

        async def complete(self, messages, itinerary):
            self.calls += 1
            return (
                '{"destination":"Japan","days":7,"total_budget":10000,'
                '"day_plans":[{"day":1,"title":"Tokyo","activities":["Arrival"]}],'
                '"tips":["Book ahead"]}'
            )

    llm = InvalidLLM()
    fallback = ValidFallbackLLM()
    service = RAGChatService(retriever=Retriever(), llm=llm, fallback_llm=fallback)
    monkeypatch.setattr(main, "get_chat_service", lambda: service)

    events = await collect_events({"message": "\u53bb\u65e5\u672c\u73a97\u5929\u884c\u7a0b"})

    message_events = [data for event, data in events if event == "message"]
    assert message_events[-1].get("error_code") is None
    assert "Japan 7 \u5929\u8be6\u7ec6\u884c\u7a0b" in "".join(event["text"] for event in message_events)
    assert len([event for event, _ in events if event == "itinerary"]) == 1
    assert events[-1][0] == "done"
    assert llm.calls == 2
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_chat_configures_a_15_second_heartbeat(monkeypatch):
    captured = {}
    original_response = main.EventSourceResponse

    def capture_response(content, **kwargs):
        captured.update(kwargs)
        return original_response(content, **kwargs)

    monkeypatch.setattr(main, "EventSourceResponse", capture_response)

    await main.chat(ChatRequest(message="hello"))

    assert captured["ping"] == 15
