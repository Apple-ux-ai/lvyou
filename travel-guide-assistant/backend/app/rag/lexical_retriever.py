"""Small in-process BM25 index for exact travel entities and numbers."""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable

_TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for value in _TOKEN_PATTERN.findall(text.casefold()):
        if all("\u4e00" <= char <= "\u9fff" for char in value):
            tokens.extend(value)
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
            tokens.extend(value[index : index + 3] for index in range(len(value) - 2))
        else:
            tokens.append(value)
    return tokens


class BM25Index:
    def __init__(self, records: Iterable[dict[str, Any]] = ()):
        self._records: list[dict[str, Any]] = []
        self._term_frequencies: list[Counter[str]] = []
        self._document_frequency: Counter[str] = Counter()
        self._average_length = 1.0
        self.replace(records)

    def replace(self, records: Iterable[dict[str, Any]]) -> None:
        self._records = list(records)
        self._term_frequencies = []
        self._document_frequency = Counter()
        total_length = 0
        for record in self._records:
            frequencies = Counter(tokenize(str(record.get("text", ""))))
            self._term_frequencies.append(frequencies)
            self._document_frequency.update(frequencies.keys())
            total_length += sum(frequencies.values())
        self._average_length = total_length / len(self._records) if self._records else 1.0

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        if not self._records or not query.strip():
            return []
        query_terms = set(tokenize(query))
        document_count = len(self._records)
        scored: list[dict[str, Any]] = []
        for index, frequencies in enumerate(self._term_frequencies):
            document_length = sum(frequencies.values()) or 1
            score = 0.0
            for term in query_terms:
                term_frequency = frequencies.get(term, 0)
                if not term_frequency:
                    continue
                document_frequency = self._document_frequency[term]
                idf = math.log(1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
                denominator = term_frequency + 1.5 * (0.25 + 0.75 * document_length / self._average_length)
                score += idf * term_frequency * 2.5 / denominator
            if score > 0:
                scored.append({**self._records[index], "lexical_score": score})
        scored.sort(key=lambda item: item["lexical_score"], reverse=True)
        return scored[:limit]
