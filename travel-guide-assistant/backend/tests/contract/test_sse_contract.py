"""SSE 协议契约测试（RED 阶段，对应缺陷 D3）

验证 /api/chat 返回 SSE 流，且：
- content-type 为 text/event-stream
- 至少包含一个 message 事件（或直接 error）
- 流必须以 done 或 error 事件终止
"""
import json

import pytest
from httpx import AsyncClient, ASGITransport

from app import main

app = main.app


@pytest.fixture(autouse=True)
def use_local_chat_service(monkeypatch):
    """SSE contract tests must never depend on a developer's local API key."""
    monkeypatch.setenv("TRAVELMATE_LLM_PROVIDER", "local")
    monkeypatch.setattr(main, "_chat_service", None)


async def collect_events(payload):
    """收集完整 SSE 流的事件列表 [(event, data_json), ...]"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("POST", "/api/chat", json=payload) as resp:
            assert resp.headers["content-type"].startswith("text/event-stream")
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
async def test_chat_returns_sse_stream():
    events = await collect_events({"message": "五一去日本玩7天"})
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_sse_must_terminate_with_done_or_error():
    events = await collect_events({"message": "五一去日本玩7天"})
    last_event, last_data = events[-1]
    assert last_event in ("done", "error")


@pytest.mark.asyncio
async def test_sse_message_event_carries_text():
    events = await collect_events({"message": "五一去日本玩7天"})
    msg_events = [e for e in events if e[0] == "message"]
    assert len(msg_events) >= 1
    assert "text" in msg_events[0][1]


@pytest.mark.asyncio
async def test_sse_done_event_carries_usage():
    events = await collect_events({"message": "你好"})
    done_events = [e for e in events if e[0] == "done"]
    assert len(done_events) == 1
    assert "usage" in done_events[0][1]
    assert "prompt_tokens" in done_events[0][1]["usage"]


@pytest.mark.asyncio
async def test_sse_done_event_carries_runtime_metrics():
    events = await collect_events({"message": "京都交通怎么安排？"})
    done_events = [data for event, data in events if event == "done"]

    metrics = done_events[0]["metrics"]
    assert metrics["embedding_ms"] >= 0
    assert metrics["retrieval_ms"] >= 0
    assert metrics["llm_ms"] >= 0
    assert isinstance(metrics["source_ids"], list)
