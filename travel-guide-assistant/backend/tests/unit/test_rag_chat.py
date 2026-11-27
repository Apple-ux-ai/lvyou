"""Focused RAG chat orchestration tests."""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.core.config import Settings
from app.models.schemas import ChatRequest
from app.rag.retriever import Document
from app.services.rag_chat import (
    ConversationStore,
    DeepSeekLLMAdapter,
    DeterministicLocalLLM,
    LLMTransportError,
    RAGChatService,
    build_default_llm,
)


VALID_ITINERARY = (
    '{"destination":"Kyoto","days":2,"total_budget":1200,'
    '"day_plans":[{"day":1,"title":"Arrival","activities":["Check in"]}],'
    '"tips":["Book ahead"]}'
)


class StubRetriever:
    def __init__(self, docs, existing_ids):
        self.docs = docs
        self.existing_ids = set(existing_ids)
        self.queries = []

    def search(self, query, top_k=5):
        self.queries.append((query, top_k))
        return self.docs

    def exists(self, source_id):
        return source_id in self.existing_ids


class SequenceLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, itinerary):
        self.calls.append({"messages": messages, "itinerary": itinerary})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class PartialStreamLLM:
    async def complete(self, messages, itinerary):
        return "fallback"

    async def stream(self, messages, itinerary):
        yield "已经生成一部分"
        raise LLMTransportError("upstream disconnected")


class CancelledStreamLLM:
    async def complete(self, messages, itinerary):
        return "fallback"

    async def stream(self, messages, itinerary):
        raise asyncio.CancelledError
        yield "unreachable"


def test_default_llm_is_local_without_an_api_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    assert isinstance(build_default_llm(Settings(_env_file=None)), DeterministicLocalLLM)


def test_default_llm_uses_deepseek_only_when_an_api_key_is_present(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    assert isinstance(
        build_default_llm(Settings(_env_file=None, travelmate_llm_provider="auto")),
        DeepSeekLLMAdapter,
    )


def test_default_llm_uses_configured_deepseek_endpoint():
    settings = Settings(
        _env_file=None,
        deepseek_api_key="test-key",
        deepseek_base_url="https://llm.example/v1",
        deepseek_model="deepseek-reasoner",
        travelmate_llm_provider="auto",
    )

    llm = build_default_llm(settings)

    assert isinstance(llm, DeepSeekLLMAdapter)
    assert llm.base_url == "https://llm.example/v1"
    assert llm.model == "deepseek-reasoner"


def test_default_llm_can_force_local_mode_with_a_configured_key():
    settings = Settings(
        _env_file=None,
        deepseek_api_key="test-key",
        travelmate_llm_provider="local",
    )

    assert isinstance(build_default_llm(settings), DeterministicLocalLLM)


@pytest.mark.asyncio
async def test_deterministic_fallback_is_explicit_chinese_degraded_answer():
    result = await DeterministicLocalLLM().complete(
        [{"role": "user", "content": "日本签证怎么办？"}],
        itinerary=False,
    )

    assert "本地模式" in result
    assert "Based on the local travel knowledge" not in result


@pytest.mark.asyncio
async def test_deepseek_adapter_sends_chat_completions_request():
    captured = {}

    def handle_request(request):
        captured["request"] = request
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "DeepSeek answer"}}]},
            request=request,
        )

    adapter = DeepSeekLLMAdapter(
        api_key="test-key",
        base_url="https://llm.example/v1",
        model="deepseek-chat",
        transport=httpx.MockTransport(handle_request),
    )
    messages = [{"role": "user", "content": "Plan a Kyoto trip"}]

    result = await adapter.complete(messages, itinerary=False)

    request = captured["request"]
    assert result == "DeepSeek answer"
    assert str(request.url) == "https://llm.example/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    assert json.loads(request.content) == {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False,
    }


@pytest.mark.asyncio
async def test_deepseek_adapter_requests_json_for_itineraries():
    captured = {}

    def handle_request(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": VALID_ITINERARY}}]},
            request=request,
        )

    adapter = DeepSeekLLMAdapter(
        api_key="test-key",
        transport=httpx.MockTransport(handle_request),
    )

    await adapter.complete([{"role": "user", "content": "Plan Kyoto"}], itinerary=True)

    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert captured["payload"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_deepseek_adapter_forwards_upstream_stream_deltas():
    captured = {}

    def handle_request(request):
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                'data: {"choices":[{"delta":{"content":"第一段"}}]}\n\n'
                'data: {"choices":[{"delta":{"content":"第二段"}}]}\n\n'
                "data: [DONE]\n\n"
            ).encode("utf-8"),
            request=request,
        )

    adapter = DeepSeekLLMAdapter(
        api_key="test-key",
        transport=httpx.MockTransport(handle_request),
    )
    chunks = [
        chunk
        async for chunk in adapter.stream(
            [{"role": "user", "content": "京都交通"}],
            itinerary=False,
        )
    ]

    assert chunks == ["第一段", "第二段"]
    assert captured["payload"]["stream"] is True


@pytest.mark.asyncio
async def test_deepseek_stream_timeout_becomes_a_typed_transport_error():
    def handle_request(request):
        raise httpx.ReadTimeout("upstream timed out", request=request)

    adapter = DeepSeekLLMAdapter(
        api_key="test-key",
        transport=httpx.MockTransport(handle_request),
    )

    with pytest.raises(LLMTransportError):
        async for _chunk in adapter.stream(
            [{"role": "user", "content": "京都交通"}],
            itinerary=False,
        ):
            pass


def test_conversation_store_evicts_least_recently_used_sessions():
    sessions = ConversationStore(max_sessions=1)

    sessions.context_for("first", [])
    sessions.context_for("second", [])

    context, expired = sessions.context_for("first", [])

    assert context == []
    assert expired is False


@pytest.mark.asyncio
async def test_rag_chat_keeps_only_relevant_existing_citations():
    retriever = StubRetriever(
        docs=[
            Document(source_id="guide-1", text="# Kyoto guide\nUseful notes", score=0.82),
            Document(source_id="low-score", text="# Ignore", score=0.29),
            Document(source_id="not-in-store", text="# Ignore", score=0.91),
        ],
        existing_ids={"guide-1", "low-score"},
    )
    service = RAGChatService(retriever=retriever, llm=SequenceLLM(["Local answer"]))

    result = await service.respond(ChatRequest(message="Tell me about Kyoto"))

    assert [(citation.source_id, citation.title) for citation in result.citations] == [("guide-1", "Kyoto guide")]
    assert retriever.queries == [("Tell me about Kyoto", 3)]


@pytest.mark.asyncio
async def test_rag_chat_passes_validated_document_text_to_llm():
    snippet = "UNIQUE_RETRIEVED_CONTEXT: Reserve the morning entry slot."
    llm = SequenceLLM(["Local answer"])
    service = RAGChatService(
        retriever=StubRetriever(
            docs=[Document(source_id="guide-1", text=f"# Kyoto guide\n{snippet}", score=0.82)],
            existing_ids={"guide-1"},
        ),
        llm=llm,
    )

    await service.respond(ChatRequest(message="Tell me about Kyoto"))

    assert snippet in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_rag_chat_includes_itinerary_schema_in_system_prompt():
    llm = SequenceLLM([VALID_ITINERARY])
    service = RAGChatService(retriever=StubRetriever([], set()), llm=llm)

    await service.respond(ChatRequest(message="去京都玩2天行程"))

    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert '"destination"' in system_prompt
    assert '"days"' in system_prompt
    assert '"day_plans"' in system_prompt
    assert "Do not use Markdown code fences" in system_prompt


@pytest.mark.asyncio
async def test_general_answer_prompt_requests_adaptive_chinese_structure():
    llm = SequenceLLM(["简短回答。"])
    service = RAGChatService(
        llm=llm,
        fallback_llm=SequenceLLM(["本地回答。"]),
        retriever=StubRetriever([], existing_ids=[]),
    )

    await service.respond(ChatRequest(message="日本签证怎么办？"))

    system_prompt = llm.calls[0]["messages"][0]["content"]
    assert "Respond in Chinese" in system_prompt
    assert "Do not emit HTML" in system_prompt
    assert "Keep a one-sentence answer as one sentence" in system_prompt


@pytest.mark.asyncio
async def test_rag_chat_instructs_a_five_day_default_for_destination_only_request():
    llm = SequenceLLM([
        '{"destination":"\u8d35\u5dde","days":5,"total_budget":8500,'
        '"day_plans":[{"day":1,"title":"\u62b5\u8fbe","activities":["\u5165\u4f4f"]}],'
        '"tips":["\u63d0\u524d\u9884\u8ba2"]}'
    ])
    service = RAGChatService(retriever=StubRetriever([], set()), llm=llm)

    result = await service.respond(ChatRequest(message="\u6211\u60f3\u53bb\u8d35\u5dde\u73a9"))

    assert result.itinerary is not None
    assert result.itinerary.days == 5
    assert "Generate exactly a 5-day itinerary" in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_rag_chat_does_not_add_default_duration_when_request_is_explicit():
    llm = SequenceLLM([VALID_ITINERARY])
    service = RAGChatService(retriever=StubRetriever([], set()), llm=llm)

    await service.respond(ChatRequest(message="\u53bb\u8d35\u5dde\u73a93\u5929"))

    assert "Generate exactly a 5-day itinerary" not in llm.calls[0]["messages"][0]["content"]


@pytest.mark.asyncio
async def test_rag_chat_allows_empty_retrieval_without_error():
    service = RAGChatService(
        retriever=StubRetriever(docs=[], existing_ids=set()),
        llm=SequenceLLM(["Local answer"]),
    )

    result = await service.respond(ChatRequest(message="An unrelated question"))

    assert result.citations == []
    assert result.error_code is None
    assert result.text == "Local answer"


@pytest.mark.asyncio
async def test_invalid_itinerary_json_is_retried_once_then_uses_fallback():
    llm = SequenceLLM(["{broken", "also not JSON"])
    fallback = SequenceLLM([VALID_ITINERARY])
    service = RAGChatService(
        retriever=StubRetriever([], set()),
        llm=llm,
        fallback_llm=fallback,
    )

    result = await service.respond(ChatRequest(message="\u53bb\u65e5\u672c\u73a97\u5929\u884c\u7a0b"))

    assert len(llm.calls) == 2
    assert len(fallback.calls) == 1
    assert result.itinerary is not None
    assert result.error_code is None
    assert "Kyoto 2 \u5929\u8be6\u7ec6\u884c\u7a0b" in result.text


@pytest.mark.asyncio
async def test_transport_failure_uses_deterministic_local_response():
    primary = SequenceLLM([LLMTransportError("network unavailable")])
    fallback = SequenceLLM(["Deterministic local answer"])
    service = RAGChatService(
        retriever=StubRetriever([], set()),
        llm=primary,
        fallback_llm=fallback,
    )

    result = await service.respond(ChatRequest(message="Hello"))

    assert result.text == "Deterministic local answer"
    assert len(primary.calls) == 1
    assert len(fallback.calls) == 1


@pytest.mark.asyncio
async def test_partial_stream_emits_error_after_preserving_received_text():
    service = RAGChatService(
        retriever=StubRetriever([], set()),
        llm=PartialStreamLLM(),
    )

    chunks = [chunk async for chunk in service.stream(ChatRequest(message="你好"))]

    assert [chunk.event for chunk in chunks] == ["message", "metrics", "error"]
    assert chunks[0].text == "已经生成一部分"
    assert chunks[-1].error_code == "llm_stream_error"
    assert chunks[1].metrics["llm_ms"] >= 0


@pytest.mark.asyncio
async def test_stream_cancellation_is_not_converted_to_a_fake_answer():
    service = RAGChatService(
        retriever=StubRetriever([], set()),
        llm=CancelledStreamLLM(),
    )

    with pytest.raises(asyncio.CancelledError):
        async for _chunk in service.stream(ChatRequest(message="你好")):
            pass


@pytest.mark.asyncio
async def test_expired_session_returns_normal_text_response():
    class Clock:
        value = datetime(2026, 8, 2, tzinfo=timezone.utc)

        def now(self):
            return self.value

    clock = Clock()
    sessions = ConversationStore(clock=clock.now)
    service = RAGChatService(
        retriever=StubRetriever([], set()),
        llm=SequenceLLM(["First answer"]),
        sessions=sessions,
    )

    await service.respond(ChatRequest(message="First", session_id="expired-session"))
    clock.value += timedelta(hours=24, seconds=1)
    result = await service.respond(ChatRequest(message="Second", session_id="expired-session"))

    assert result.session_expired is True
    assert result.itinerary is None
    assert result.text


@pytest.mark.asyncio
async def test_context_keeps_last_three_turns_and_caps_long_history_text():
    llm = SequenceLLM(["Answer"])
    history = []
    for turn in range(4):
        history.extend(
            [
                {"role": "user", "content": f"user-{turn}"},
                {"role": "assistant", "content": "x" * 9000 if turn == 3 else f"assistant-{turn}"},
            ]
        )
    service = RAGChatService(retriever=StubRetriever([], set()), llm=llm)

    await service.respond(ChatRequest(message="Current", history=history))

    dialogue = [message for message in llm.calls[0]["messages"] if message["role"] in {"user", "assistant"}]
    previous_dialogue = dialogue[:-1]
    assert len(previous_dialogue) == 6
    assert all(len(message["content"]) <= 8000 for message in dialogue)
    assert "user-0" not in [message["content"] for message in previous_dialogue]
