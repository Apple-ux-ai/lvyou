"""向量检索器（内存版）：空库 / 阈值 / Top-K / 引用完整性（缺陷 H2 修复）

生产环境将替换为 Chroma/Qdrant 实现，接口保持一致。
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Document:
    source_id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class Retriever:
    def __init__(self, docs: List[Document], min_score: float = 0.3):
        self._docs = docs
        self.min_score = min_score

    def search(self, query: str, top_k: int = 5) -> List[Document]:
        """按相关度降序返回 Top-K；空库或全部低于阈值时返回空列表。"""
        scored = [d for d in self._docs if d.score >= self.min_score]
        scored.sort(key=lambda d: d.score, reverse=True)
        return scored[:top_k]

    def exists(self, source_id: str) -> bool:
        """引用完整性：source_id 必须存在于库中"""
        return any(d.source_id == source_id for d in self._docs)
