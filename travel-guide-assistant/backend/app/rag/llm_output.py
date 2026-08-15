"""LLM 输出解析：坏 JSON 降级链（缺陷 H1 修复）

合法 Itinerary JSON → type="itinerary"
非法 JSON / schema 不匹配 → type="text" + error_code="invalid_json"（不崩溃）
"""
import json
from dataclasses import dataclass
from typing import Optional

from app.models.schemas import Itinerary


@dataclass
class ParseResult:
    type: str  # "itinerary" | "text"
    itinerary: Optional[Itinerary] = None
    text: Optional[str] = None
    error_code: Optional[str] = None


def parse_llm_output(raw: str) -> ParseResult:
    """解析 LLM 输出；任何异常都降级为纯文本，绝不抛异常。"""
    if not raw or not raw.strip():
        return ParseResult(type="text", text=raw, error_code="invalid_json")

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return ParseResult(type="text", text=raw, error_code="invalid_json")

    if not isinstance(data, dict):
        return ParseResult(type="text", text=raw, error_code="invalid_json")

    try:
        itinerary = Itinerary.model_validate(data)
    except Exception:
        return ParseResult(type="text", text=raw, error_code="invalid_json")

    return ParseResult(type="itinerary", itinerary=itinerary)
