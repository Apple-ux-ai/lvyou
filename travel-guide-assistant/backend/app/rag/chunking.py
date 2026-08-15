"""Knowledge document parsing and section-aware chunking."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

CHUNKING_VERSION = "section-v1"
DEFAULT_TARGET_CHARS = 420
DEFAULT_OVERLAP_CHARS = 80
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class ParsedChunk:
    text: str
    index: int
    title: str
    section: str


def split_document(
    content: str,
    source_id: str,
    suffix: str = ".md",
    target_chars: int = DEFAULT_TARGET_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[ParsedChunk]:
    """Parse a knowledge file into bounded chunks carrying section context."""
    if target_chars < 1:
        raise ValueError("target_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= target_chars:
        raise ValueError("overlap_chars must be between 0 and target_chars - 1")
    units = _json_units(content) if suffix.lower() == ".json" else []
    if not units:
        units = _markdown_units(content, source_id)
    if not units:
        return []

    packed = _pack_units(units, target_chars, overlap_chars)
    return [
        ParsedChunk(text=text, index=index, title=title, section=section)
        for index, (text, title, section) in enumerate(packed)
    ]


def split_chunks(content: str, source_id: str = "document", suffix: str = ".md") -> list[str]:
    """Compatibility wrapper used by the ingestion CLI and older callers."""
    return [chunk.text for chunk in split_document(content, source_id, suffix)]


def _markdown_units(content: str, source_id: str) -> list[tuple[str, str, str]]:
    stack: list[str] = []
    title = source_id
    units: list[tuple[str, str, str]] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        body = "\n".join(line.strip() for line in buffer if line.strip()).strip()
        if body:
            section = " > ".join(stack)
            visible_section = section if section != title else ""
            prefix = f"{title} > {visible_section}" if visible_section else title
            units.append((f"{prefix}\n{body}", title, section))
        buffer.clear()

    for raw_line in content.replace("\r\n", "\n").split("\n"):
        line = raw_line.strip()
        heading = _HEADING_PATTERN.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            heading_text = heading.group(2).strip()
            if not stack:
                title = heading_text
            stack[:] = stack[: level - 1]
            stack.append(heading_text)
            continue
        if not line:
            flush()
            continue
        buffer.append(line)
    flush()
    return units


def _json_units(content: str) -> list[tuple[str, str, str]]:
    try:
        value = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return []

    lines: list[str] = []

    def walk(current: Any, path: list[str]) -> None:
        if isinstance(current, dict):
            for key, child in current.items():
                walk(child, [*path, str(key)])
            return
        if isinstance(current, list):
            for index, child in enumerate(current, 1):
                walk(child, [*path, str(index)])
            return
        if current is not None:
            label = " > ".join(path) or "content"
            lines.append(f"{label}: {current}")

    walk(value, [])
    if not lines:
        return []
    title = " > ".join(lines[0].split(":", 1)[0].split(" > ")[:1]) or "document"
    return [(f"{title}\n{line}", title, line.split(":", 1)[0]) for line in lines]


def _pack_units(
    units: list[tuple[str, str, str]], target_chars: int, overlap_chars: int
) -> list[tuple[str, str, str]]:
    packed: list[tuple[str, str, str]] = []
    current = ""
    current_title = ""
    current_section = ""

    def emit(text: str, title: str, section: str) -> None:
        if text.strip():
            packed.append((text.strip(), title, section))

    for unit, title, section in units:
        if len(unit) > target_chars:
            if current:
                emit(current, current_title, current_section)
                current = ""
            context, separator, body = unit.partition("\n")
            if separator:
                body_target = max(1, target_chars - len(context) - 1)
                body_overlap = min(overlap_chars, max(0, body_target - 1))
                pieces = _split_long_text(body, body_target, body_overlap)
                for piece in pieces:
                    emit(f"{context}\n{piece}", title, section)
            else:
                for piece in _split_long_text(unit, target_chars, overlap_chars):
                    emit(piece, title, section)
            continue

        candidate = f"{current}\n{unit}" if current else unit
        if current and len(candidate) > target_chars:
            emit(current, current_title, current_section)
            available_overlap = target_chars - len(unit) - 1
            overlap_size = min(overlap_chars, max(0, available_overlap))
            overlap = current[-overlap_size:].strip() if overlap_size else ""
            current = f"{overlap}\n{unit}" if overlap else unit
            current_title = title
            current_section = section
        else:
            current = candidate
            current_title = current_title or title
            current_section = current_section or section
    if current:
        emit(current, current_title, current_section)
    return packed


def _split_long_text(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    result: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_chars, len(text))
        if end < len(text):
            boundary = max(text.rfind(mark, start + target_chars // 2, end) for mark in ("\n", "。", "！", "？", ";", "；"))
            if boundary > start:
                end = boundary + 1
        piece = text[start:end].strip()
        if piece:
            result.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap_chars)
    return result
