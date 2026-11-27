"""FastAPI entry point for travel chat and trip persistence."""
import asyncio
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.core.config import load_settings
from app.core.rate_limit import ChatRateLimitGuard, ConcurrencyLimiter, get_client_key
from app.models.schemas import ChatRequest, Itinerary, Trip
from app.services.rag_chat import create_default_chat_service
from app.services.trips import trip_store
from app.services.trip_checks import check_trip

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
settings = load_settings()

chat_rate_limit_guard = ChatRateLimitGuard(
    per_ip_limit=settings.travelmate_rate_limit_per_window,
    per_ip_window_seconds=settings.travelmate_rate_limit_window_seconds,
    global_limit=settings.travelmate_global_chat_limit,
    global_window_seconds=settings.travelmate_global_chat_window_seconds,
)
chat_concurrency_limiter = ConcurrencyLimiter(settings.travelmate_max_concurrent_chats)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await validate_index_on_startup()
    yield


app = FastAPI(title="TravelMate API", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in settings.travelmate_cors_origins.split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _usage(prompt_tokens: int = 0, completion_tokens: int = 0) -> dict:
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens}


def _stream_text_chunks(text: str, chunk_size: int = 160):
    if not text:
        yield ""
        return
    for start in range(0, len(text), chunk_size):
        yield text[start : start + chunk_size]


_chat_service = None


def get_chat_service():
    """Lazy construction keeps the route easy to monkeypatch in tests."""
    global _chat_service
    if _chat_service is None:
        _chat_service = create_default_chat_service()
    return _chat_service


async def _chat_stream(payload: ChatRequest):
    """Translate a RAG chat result into the existing SSE event contract."""
    chat_id = uuid.uuid4().hex[:12]
    started_at = time.perf_counter()
    answer_parts = []
    metrics: dict[str, object] = {}
    try:
        service = get_chat_service()
        stream_method = getattr(service, "stream", None)
        if callable(stream_method):
            async for chunk in stream_method(payload):
                citations = [citation.model_dump() for citation in chunk.citations]
                if chunk.event == "message":
                    answer_parts.append(chunk.text)
                    message_data = {"text": chunk.text, "citations": citations}
                    if chunk.error_code:
                        message_data["error_code"] = chunk.error_code
                    yield {
                        "event": "message",
                        "data": json.dumps(message_data, ensure_ascii=False),
                    }
                elif chunk.event == "itinerary" and chunk.itinerary is not None:
                    itinerary_data = chunk.itinerary.model_dump()
                    itinerary_data["citations"] = citations
                    yield {
                        "event": "itinerary",
                        "data": json.dumps(itinerary_data, ensure_ascii=False),
                    }
                elif chunk.event == "error":
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {
                                "code": chunk.error_code or "chat_error",
                                "message": _public_error_message(chunk.error_code),
                            },
                            ensure_ascii=False,
                        ),
                    }
                    return
                elif chunk.event == "metrics":
                    metrics = dict(chunk.metrics)
        else:
            response = await service.respond(payload)
            metrics = dict(response.metrics)
            for chunk in _stream_text_chunks(response.text):
                answer_parts.append(chunk)
                message_data = {
                    "text": chunk,
                    "citations": [citation.model_dump() for citation in response.citations],
                }
                if response.error_code:
                    message_data["error_code"] = response.error_code
                yield {"event": "message", "data": json.dumps(message_data, ensure_ascii=False)}

            if response.itinerary is not None:
                itinerary_data = response.itinerary.model_dump()
                itinerary_data["citations"] = [citation.model_dump() for citation in response.citations]
                yield {"event": "itinerary", "data": json.dumps(itinerary_data, ensure_ascii=False)}

        yield {
            "event": "done",
            "data": json.dumps(
                {
                    "id": chat_id,
                    "session_id": payload.session_id,
                    "usage": _usage(
                        prompt_tokens=len(payload.message),
                        completion_tokens=len("".join(answer_parts)),
                    ),
                    "metrics": metrics,
                }
            ),
        }
        logger.info(
            "chat request_id=%s embedding_ms=%.1f retrieval_ms=%.1f llm_ms=%.1f "
            "top_score=%.4f source_ids=%s embedding_model=%s llm_provider=%s llm_model=%s total_ms=%.1f",
            chat_id,
            float(metrics.get("embedding_ms", 0.0)),
            float(metrics.get("retrieval_ms", 0.0)),
            float(metrics.get("llm_ms", 0.0)),
            float(metrics.get("top_score", 0.0)),
            metrics.get("source_ids", []),
            metrics.get("embedding_model", "unknown"),
            metrics.get("llm_provider", "unknown"),
            metrics.get("llm_model", "unknown"),
            float(metrics.get("total_ms", (time.perf_counter() - started_at) * 1000)),
        )
    except asyncio.CancelledError:
        logger.info("chat request_id=%s cancelled", chat_id)
        raise
    except Exception:
        logger.exception("chat request_id=%s failed", chat_id)
        yield {
            "event": "error",
            "data": json.dumps(
                {"code": "server_error", "message": "服务暂时不可用，请稍后重试。"},
                ensure_ascii=False,
            ),
        }


async def _limited_chat_stream(payload: ChatRequest):
    async for event in chat_concurrency_limiter.stream(_chat_stream(payload)):
        yield event


def _public_error_message(code: str | None) -> str:
    messages = {
        "session_expired": "会话已过期，请重新开始对话。",
        "llm_stream_error": "回答生成中断，请稍后重试。",
    }
    return messages.get(code or "", "服务暂时不可用，请稍后重试。")


@app.get("/api/health")
async def health():
    try:
        index = get_chat_service().retriever.health()
        manifest = index.get("manifest") or {}
        healthy = index.get("embedding_compatible", True) and manifest.get("compatible", True)
        return {"status": "ok" if healthy else "degraded", "index": index}
    except Exception:
        logger.exception("health check failed")
        return {"status": "degraded", "index": {"available": False}}


async def validate_index_on_startup() -> None:
    try:
        index = get_chat_service().retriever.health()
        manifest = index.get("manifest") or {}
        if not index.get("embedding_compatible", True) or not manifest.get("compatible", True):
            logger.warning(
                "index requires rebuild: persist_dir=%s manifest_status=%s embedding_compatible=%s",
                index.get("persist_dir"),
                manifest.get("status", "unknown"),
                index.get("embedding_compatible"),
            )
    except Exception:
        logger.exception("index startup validation failed")


@app.post("/api/trips", response_model=Trip, status_code=201)
async def create_trip(itinerary: Itinerary) -> Trip:
    return trip_store.create(itinerary)


@app.post("/api/trips/check")
async def review_trip(itinerary: Itinerary) -> dict:
    return check_trip(itinerary)


@app.get("/api/trips", response_model=list[Trip])
async def list_trips() -> list[Trip]:
    return trip_store.list()


@app.get("/api/trips/{trip_id}", response_model=Trip)
async def get_trip(trip_id: str) -> Trip:
    trip = trip_store.get(trip_id)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@app.put("/api/trips/{trip_id}", response_model=Trip)
async def update_trip(trip_id: str, itinerary: Itinerary) -> Trip:
    trip = trip_store.update(trip_id, itinerary)
    if trip is None:
        raise HTTPException(status_code=404, detail="Trip not found")
    return trip


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request = None):
    if settings.travelmate_rate_limit_enabled:
        client_key = get_client_key(request) if request is not None else "direct-call"
        decision = await chat_rate_limit_guard.check(client_key)
        if not decision.allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "code": "rate_limited",
                    "message": "请求太频繁，请稍后再试。",
                    "retry_after": decision.retry_after,
                },
                headers={"Retry-After": str(decision.retry_after)},
            )

    return EventSourceResponse(_limited_chat_stream(payload), ping=15)
