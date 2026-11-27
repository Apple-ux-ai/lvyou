"""知识库入库器（内存版）：幂等性 / 版本替换（缺陷 M4 修复）

- 同一 (source_id, version) 重复入库不产生重复 chunk
- version 递增后旧 chunk 被替换
- 生产环境将持久化到 Chroma/Qdrant
"""
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class Chunk:
    source_id: str
    text: str
    version: int
    index: int


@dataclass
class ChunkStore:
    chunks: Dict[str, List[Chunk]] = field(default_factory=dict)

    def get(self, source_id: str) -> List[Chunk]:
        return self.chunks.get(source_id, [])

    def replace(self, source_id: str, chunks: List[Chunk]) -> None:
        self.chunks[source_id] = chunks


@dataclass
class IngestResult:
    source_id: str
    chunk_count: int
    version: int


class Indexer:
    def __init__(self, store: ChunkStore):
        self.store = store

    def ingest(self, source_id: str, content: str, version: int = 1) -> IngestResult:
        """入库；幂等——同版本重复入库不产生重复 chunk。"""
        existing = self.store.get(source_id)
        # 若已有同版本数据且 chunk 数一致 → 视为重复入库，直接返回
        if existing and existing[0].version == version:
            expected = len([l for l in content.splitlines() if l.strip()])
            if len(existing) == expected:
                return IngestResult(source_id=source_id, chunk_count=len(existing), version=version)

        lines = [l for l in content.splitlines() if l.strip()]
        if not lines:
            lines = [content.strip()] if content.strip() else []

        chunks = [
            Chunk(source_id=source_id, text=line, version=version, index=i)
            for i, line in enumerate(lines)
        ]
        self.store.replace(source_id, chunks)
        return IngestResult(source_id=source_id, chunk_count=len(chunks), version=version)

    def count_chunks(self, source_id: str) -> int:
        return len(self.store.get(source_id))

    def get_chunks(self, source_id: str) -> List[Chunk]:
        return self.store.get(source_id)
