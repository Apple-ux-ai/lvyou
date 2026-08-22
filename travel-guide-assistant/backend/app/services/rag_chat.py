"""Composable RAG chat orchestration with local and DeepSeek-compatible LLMs."""
from __future__ import annotations

import os
import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Callable, Protocol

import httpx

from app.core.config import BACKEND_ROOT, Settings, load_settings
from app.models.schemas import ChatRequest, Citation, Itinerary
from app.rag.chroma_store import ChromaRetriever
from app.rag.index_versions import resolve_index_path
from app.rag.llm_output import parse_llm_output
from app.rag.pipeline import build_mock_itinerary, detect_days, detect_destination, is_plan_intent
from app.rag.retriever import Document

logger = logging.getLogger(__name__)

MIN_SCORE = 0.3
MAX_TURNS = 3
# A conservative ~4 characters per token approximation for the 2,000-token budget.
MAX_TEXT_CHARS = 8_000
# Keep retrieved evidence bounded so it cannot crowd out the dialogue window.
MAX_RETRIEVED_CONTEXT_CHARS = 4_000
SESSION_TTL = timedelta(hours=24)
ITINERARY_JSON_INSTRUCTION = (
    'Return exactly one valid JSON object with this shape: '
    '{"destination":"string","days":1,"total_budget":0,'
    '"day_plans":[{"day":1,"title":"string","activities":["string"],'
    '"transport":"string or null","budget":0}],"tips":["string"]}. '
    'days and day_plans[].day must be positive integers. '
    'total_budget and day_plans[].budget may be null. '
    'Do not use Markdown code fences or add text outside the JSON object.'
)
ITINERARY_TEXT_INTRO = "我把行程拆成了左侧可阅读说明，右侧是可保存和编辑的结构化版本。"
GENERAL_ANSWER_INSTRUCTION = (
    "Respond in Chinese. Start with a direct conclusion. Add at most three short sections "
    "with Markdown headings and ordered or unordered lists only when they improve clarity. "
    "Use '- **标签**：值' for compact facts and one '> 提醒' block only for a material caveat. "
    "Do not emit HTML, Markdown tables, decorative headings, or filler sections. "
    "Keep a one-sentence answer as one sentence. Use supplied sources when available."
)


class LLMTransportError(RuntimeError):
    """Raised when an LLM request cannot produce a usable response."""


class ChatLLM(Protocol):
    async def complete(self, messages: list[dict[str, str]], itinerary: bool) -> str:
        """Return plain text or an Itinerary JSON object, depending on intent."""

    def stream(self, messages: list[dict[str, str]], itinerary: bool) -> AsyncIterator[str]:
        """Yield upstream text deltas when the provider supports streaming."""


class DeepSeekLLMAdapter:
    """Small DeepSeek-compatible Chat Completions adapter selected by environment."""

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.api_key = api_key
        configured_base_url = (base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        if configured_base_url == "https://api.deepseek.com/v1":
            configured_base_url = "https://api.deepseek.com"
        self.base_url = configured_base_url
        self.model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.timeout = timeout
        self.transport = transport

    async def complete(self, messages: list[dict[str, str]], itinerary: bool) -> str:
        try:
            payload = {"model": self.model, "messages": messages, "stream": False}
            if itinerary:
                payload["response_format"] = {"type": "json_object"}
                payload["thinking"] = {"type": "disabled"}
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("LLM response did not contain text")
            return content
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text[:240].replace("\n", " ")
            raise LLMTransportError(f"DeepSeek HTTP {status}: {detail}") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMTransportError(f"DeepSeek request failed: {exc}") from exc

    async def stream(self, messages: list[dict[str, str]], itinerary: bool) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
        }
        if itinerary:
            payload["response_format"] = {"type": "json_object"}
            payload["thinking"] = {"type": "disabled"}

        emitted = False
        try:
            async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line or line.startswith(":"):
                            continue
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        event = json.loads(data)
                        choices = event.get("choices") or []
                        delta = choices[0].get("delta") if choices else None
                        content = delta.get("content") if isinstance(delta, dict) else None
                        if isinstance(content, str) and content:
                            emitted = True
                            yield content
            if not emitted:
                raise LLMTransportError("DeepSeek stream contained no text")
        except asyncio.CancelledError:
            raise
        except LLMTransportError:
            raise
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            detail = exc.response.text[:240].replace("\n", " ")
            raise LLMTransportError(f"DeepSeek HTTP {status}: {detail}") from exc
        except (httpx.HTTPError, json.JSONDecodeError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMTransportError(f"DeepSeek stream failed: {exc}") from exc


class DeterministicLocalLLM:
    """Offline fallback used without an API key and after transport failures."""

    async def complete(self, messages: list[dict[str, str]], itinerary: bool) -> str:
        user_text = next(
            (message["content"] for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if itinerary:
            destination = detect_destination(user_text) or "Destination"
            days = detect_days(user_text) or 5
            return build_mock_itinerary(destination, days).model_dump_json()
        return (
            "本地模式暂时无法调用在线模型。"
            f"关于“{user_text[:300]}”，请稍后重试，或补充更具体的问题以便使用本地规则处理。"
        )


def build_default_llm(settings: Settings | None = None) -> ChatLLM:
    """Select the remote adapter only when an environment key is explicitly present."""
    configured = settings or load_settings()
    if configured.travelmate_llm_provider == "local":
        return DeterministicLocalLLM()
    if configured.deepseek_api_key:
        return DeepSeekLLMAdapter(
            api_key=configured.deepseek_api_key.get_secret_value(),
            base_url=configured.deepseek_base_url,
            model=configured.deepseek_model,
        )
    return DeterministicLocalLLM()


@dataclass
class _Session:
    created_at: datetime
    last_access: datetime
    history: list[dict[str, str]] = field(default_factory=list)


class ConversationStore:
    """In-memory session window with a fixed 24-hour lifetime."""

    def __init__(
        self,
        clock: Callable[[], datetime] | None = None,
        max_sessions: int | None = None,
    ):
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.max_sessions = max_sessions or load_settings().travelmate_max_sessions
        self._sessions: dict[str, _Session] = {}

    def context_for(self, session_id: str | None, supplied_history: list[dict]) -> tuple[list[dict[str, str]], bool]:
        supplied = self._normalize_history(supplied_history)
        if not session_id:
            return supplied, False

        now = self._clock()
        session = self._sessions.get(session_id)
        if session is not None and now - session.created_at >= SESSION_TTL:
            del self._sessions[session_id]
            return [], True
        if session is None:
            self._sessions[session_id] = _Session(
                created_at=now,
                last_access=now,
                history=supplied,
            )
            self._evict_if_needed()
            return supplied, False
        session.last_access = now
        return session.history, False

    def record(self, session_id: str | None, user_text: str, assistant_text: str) -> None:
        if not session_id:
            return
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.history = (session.history + [
            {"role": "user", "content": _cap_text(user_text)},
            {"role": "assistant", "content": _cap_text(assistant_text)},
        ])[-(MAX_TURNS * 2):]
        session.last_access = self._clock()

    def _evict_if_needed(self) -> None:
        while len(self._sessions) > self.max_sessions:
            oldest_id = min(
                self._sessions,
                key=lambda session_id: self._sessions[session_id].last_access,
            )
            del self._sessions[oldest_id]

    @staticmethod
    def _normalize_history(history: list[dict]) -> list[dict[str, str]]:
        normalized = []
        for item in history:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role not in {"user", "assistant"}:
                continue
            content = item.get("content", item.get("text", ""))
            if not isinstance(content, str):
                continue
            normalized.append({"role": role, "content": _cap_text(content)})
        return normalized[-(MAX_TURNS * 2):]


@dataclass
class ChatResult:
    text: str
    citations: list[Citation]
    itinerary: Itinerary | None = None
    error_code: str | None = None
    session_expired: bool = False
    metrics: dict[str, object] = field(default_factory=dict)


@dataclass
class ChatStreamChunk:
    event: str
    text: str = ""
    citations: list[Citation] = field(default_factory=list)
    itinerary: Itinerary | None = None
    error_code: str | None = None
    error_message: str | None = None
    metrics: dict[str, object] = field(default_factory=dict)


class RAGChatService:
    def __init__(
        self,
        retriever: ChromaRetriever,
        llm: ChatLLM,
        fallback_llm: ChatLLM | None = None,
        sessions: ConversationStore | None = None,
    ):
        self.retriever = retriever
        self.llm = llm
        self.fallback_llm = fallback_llm or DeterministicLocalLLM()
        self.sessions = sessions or ConversationStore()
        settings = load_settings()
        self.min_score = settings.travelmate_retrieval_min_score
        self.retrieval_top_k = settings.travelmate_retrieval_top_k

    async def respond(self, payload: ChatRequest) -> ChatResult:
        started = time.perf_counter()
        user_text = _cap_text(payload.message)
        history, expired = self.sessions.context_for(payload.session_id, payload.history)
        if expired:
            return ChatResult(
                text="This conversation has expired after 24 hours. Please start a new session.",
                citations=[],
                session_expired=True,
            )

        retrieval_started = time.perf_counter()
        citations, documents = self._retrieve_context(user_text)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        planning = is_plan_intent(user_text)
        messages = self._build_messages(history, user_text, citations, documents, planning)

        llm_started = time.perf_counter()
        if planning:
            result = await self._respond_with_itinerary(messages, citations)
        else:
            result = ChatResult(text=await self._complete(messages, itinerary=False), citations=citations)
        llm_ms = (time.perf_counter() - llm_started) * 1000

        self.sessions.record(payload.session_id, user_text, result.text)
        result.metrics = self._runtime_metrics(
            started,
            retrieval_ms,
            llm_ms,
            citations,
        )
        return result

    async def stream(self, payload: ChatRequest) -> AsyncIterator[ChatStreamChunk]:
        """Stream text deltas while keeping itinerary parsing atomic."""
        started = time.perf_counter()
        user_text = _cap_text(payload.message)
        history, expired = self.sessions.context_for(payload.session_id, payload.history)
        if expired:
            yield ChatStreamChunk(
                event="error",
                error_code="session_expired",
                error_message="This conversation has expired. Please start a new session.",
            )
            return

        retrieval_started = time.perf_counter()
        citations, documents = self._retrieve_context(user_text)
        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
        planning = is_plan_intent(user_text)
        messages = self._build_messages(history, user_text, citations, documents, planning)

        llm_started = time.perf_counter()
        if planning:
            result = await self._stream_itinerary(messages, citations)
            llm_ms = (time.perf_counter() - llm_started) * 1000
            for text in _split_text_chunks(result.text):
                yield ChatStreamChunk(
                    event="message",
                    text=text,
                    citations=citations,
                    error_code=result.error_code,
                )
            if result.itinerary is not None:
                yield ChatStreamChunk(
                    event="itinerary",
                    citations=citations,
                    itinerary=result.itinerary,
                )
            self.sessions.record(payload.session_id, user_text, result.text)
            yield ChatStreamChunk(
                event="metrics",
                metrics=self._runtime_metrics(started, retrieval_ms, llm_ms, citations),
            )
            return

        parts: list[str] = []
        try:
            async for text in self._stream_model_text(messages, itinerary=False):
                if not text:
                    continue
                parts.append(text)
                yield ChatStreamChunk(event="message", text=text, citations=citations)
        except LLMTransportError:
            if parts:
                yield ChatStreamChunk(
                    event="metrics",
                    metrics=self._runtime_metrics(
                        started,
                        retrieval_ms,
                        (time.perf_counter() - llm_started) * 1000,
                        citations,
                    ),
                )
                yield ChatStreamChunk(
                    event="error",
                    error_code="llm_stream_error",
                    error_message="The answer stream was interrupted.",
                )
                return
            raise

        answer = "".join(parts)
        if not answer:
            answer = "暂时没有生成有效回答，请稍后重试。"
            yield ChatStreamChunk(event="message", text=answer, citations=citations)
        self.sessions.record(payload.session_id, user_text, answer)
        yield ChatStreamChunk(
            event="metrics",
            metrics=self._runtime_metrics(
                started,
                retrieval_ms,
                (time.perf_counter() - llm_started) * 1000,
                citations,
            ),
        )

    async def _respond_with_itinerary(self, messages: list[dict[str, str]], citations: list[Citation]) -> ChatResult:
        for _attempt in range(2):
            parsed = parse_llm_output(await self._complete(messages, itinerary=True))
            if parsed.type == "itinerary" and parsed.itinerary is not None:
                return ChatResult(
                    text=format_itinerary_text(parsed.itinerary),
                    citations=citations,
                    itinerary=parsed.itinerary,
                )

        fallback = parse_llm_output(await self.fallback_llm.complete(messages, itinerary=True))
        if fallback.type == "itinerary" and fallback.itinerary is not None:
            return ChatResult(
                text=format_itinerary_text(fallback.itinerary),
                citations=citations,
                itinerary=fallback.itinerary,
            )

        return ChatResult(
            text="\u884c\u7a0b\u6570\u636e\u751f\u6210\u5931\u8d25\uff0c\u8bf7\u91cd\u65b0\u8f93\u5165\u76ee\u7684\u5730\u548c\u51fa\u884c\u5929\u6570\u3002",
            citations=citations,
            error_code="invalid_json",
        )

    async def _stream_itinerary(
        self,
        messages: list[dict[str, str]],
        citations: list[Citation],
    ) -> ChatResult:
        for _attempt in range(2):
            raw_parts: list[str] = []
            async for text in self._stream_model_text(messages, itinerary=True):
                raw_parts.append(text)
            parsed = parse_llm_output("".join(raw_parts))
            if parsed.type == "itinerary" and parsed.itinerary is not None:
                return ChatResult(
                    text=format_itinerary_text(parsed.itinerary),
                    citations=citations,
                    itinerary=parsed.itinerary,
                )

        fallback = parse_llm_output(await self.fallback_llm.complete(messages, itinerary=True))
        if fallback.type == "itinerary" and fallback.itinerary is not None:
            return ChatResult(
                text=format_itinerary_text(fallback.itinerary),
                citations=citations,
                itinerary=fallback.itinerary,
            )
        return ChatResult(
            text="行程数据生成失败，请重新输入目的地和出行天数。",
            citations=citations,
            error_code="invalid_json",
        )

    async def _complete(self, messages: list[dict[str, str]], itinerary: bool) -> str:
        try:
            return await self.llm.complete(messages, itinerary)
        except LLMTransportError as exc:
            logger.warning("Primary LLM failed; using local fallback: %s", exc)
            return await self.fallback_llm.complete(messages, itinerary)

    async def _stream_model_text(
        self,
        messages: list[dict[str, str]],
        itinerary: bool,
    ) -> AsyncIterator[str]:
        stream_method = getattr(self.llm, "stream", None)
        if callable(stream_method):
            emitted = False
            try:
                async for text in stream_method(messages, itinerary):
                    if text:
                        emitted = True
                        yield text
                if emitted:
                    return
            except LLMTransportError as exc:
                logger.warning("Primary LLM stream failed; using local fallback: %s", exc)
                if emitted:
                    raise

        yield await self._complete(messages, itinerary)

    def _runtime_metrics(
        self,
        started: float,
        retrieval_ms: float,
        llm_ms: float,
        citations: list[Citation],
    ) -> dict[str, object]:
        retrieval_metrics = getattr(self.retriever, "last_search_metrics", {}) or {}
        source_ids = [citation.source_id for citation in citations]
        return {
            "embedding_ms": float(retrieval_metrics.get("embedding_ms", 0.0)),
            "retrieval_ms": round(retrieval_ms, 3),
            "llm_ms": round(llm_ms, 3),
            "total_ms": round((time.perf_counter() - started) * 1000, 3),
            "top_score": float(retrieval_metrics.get("top_score", 0.0)),
            "source_ids": source_ids,
            "embedding_model": retrieval_metrics.get(
                "embedding_model",
                getattr(self.retriever, "embedding_model", "unknown"),
            ),
            "llm_provider": "deepseek" if isinstance(self.llm, DeepSeekLLMAdapter) else "local",
            "llm_model": getattr(self.llm, "model", "deterministic-local"),
        }

    def _retrieve_context(self, query: str) -> tuple[list[Citation], list[Document]]:
        try:
            docs = self.retriever.search(query, top_k=self.retrieval_top_k)
        except Exception:
            if hasattr(self.retriever, "last_search_metrics"):
                self.retriever.last_search_metrics = {}
            return [], []

        citations = []
        validated_documents = []
        for doc in docs:
            if not isinstance(doc, Document) or doc.score < self.min_score:
                continue
            try:
                if not self.retriever.exists(doc.source_id):
                    continue
            except Exception:
                continue
            title = str(doc.metadata.get("title", "")) or (
                doc.text.splitlines()[0] if doc.text else ""
            ).lstrip("# ").strip()
            citations.append(Citation(source_id=doc.source_id, title=(title or doc.source_id)[:80]))
            validated_documents.append(doc)
        return citations, validated_documents

    @staticmethod
    def _build_messages(
        history: list[dict[str, str]],
        user_text: str,
        citations: list[Citation],
        documents: list[Document],
        itinerary: bool,
    ) -> list[dict[str, str]]:
        sources = "; ".join(f"{citation.source_id}: {citation.title}" for citation in citations) or "No sources retrieved."
        context = _build_retrieved_context(documents)
        instruction = ITINERARY_JSON_INSTRUCTION if itinerary else GENERAL_ANSWER_INSTRUCTION
        instruction += (
            " Only use verified retrieved context for factual claims. "
            "If the context is empty or insufficient, say what is uncertain instead of inventing a citation."
        )
        if itinerary and detect_days(user_text) is None:
            instruction += " Generate exactly a 5-day itinerary because the traveller did not specify a duration."
        return [
            {"role": "system", "content": f"{instruction} Sources: {sources}\nRetrieved context:\n{context}"},
            *history,
            {"role": "user", "content": user_text},
        ]


def create_default_chat_service() -> RAGChatService:
    settings = load_settings()
    configured_root = Path(settings.travelmate_index_root) if settings.travelmate_index_root else None
    if configured_root is not None and not configured_root.is_absolute():
        configured_root = BACKEND_ROOT / configured_root
    data_dir = resolve_index_path(
        configured_root,
        settings.travelmate_index_version or None,
        BACKEND_ROOT / "chroma_data",
    )
    return RAGChatService(
        retriever=ChromaRetriever(persist_dir=str(data_dir), collection="knowledge"),
        llm=build_default_llm(settings),
    )


def format_itinerary_text(itinerary: Itinerary) -> str:
    lines = [
        ITINERARY_TEXT_INTRO,
        "",
        f"## {itinerary.destination} {itinerary.days} 天详细行程",
    ]
    if itinerary.total_budget is not None:
        lines.append(f"- **预算参考**：约 ¥{itinerary.total_budget:,} /人")
    lines.append("- **操作提示**：右侧已同步生成结构化行程，可展开每天安排、保存或继续编辑。")

    for day in itinerary.day_plans:
        lines.extend(["", f"### D{day.day}｜{day.title}"])
        activities = [activity for activity in day.activities if activity]
        if activities:
            lines.extend(f"{index}. {activity}" for index, activity in enumerate(activities, 1))
        if day.transport:
            lines.append(f"- **交通建议**：{day.transport}")
        if day.budget is not None:
            lines.append(f"- **当日预算**：约 ¥{day.budget:,} /人")

    if itinerary.tips:
        lines.extend(["", "### 出行提醒"])
        lines.extend(f"- {tip}" for tip in itinerary.tips if tip)

    return "\n".join(lines).strip()


def _cap_text(value: str) -> str:
    return value[:MAX_TEXT_CHARS]


def _split_text_chunks(text: str, chunk_size: int = 160) -> list[str]:
    if not text:
        return [""]
    return [text[start : start + chunk_size] for start in range(0, len(text), chunk_size)]


def _build_retrieved_context(documents: list[Document]) -> str:
    if not documents:
        return "No document text retrieved."

    remaining = MAX_RETRIEVED_CONTEXT_CHARS
    parts = []
    for document in documents:
        if remaining <= 0:
            break
        text = document.text[:remaining]
        if not text:
            continue
        part = f"[{document.source_id}]\n{text}"
        parts.append(part)
        remaining -= len(text)
    return "\n\n".join(parts) or "No document text retrieved."
