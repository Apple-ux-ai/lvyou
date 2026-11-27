"""ingest 幂等性测试（RED 阶段，对应缺陷 M4）"""
from app.rag.indexer import Indexer, ChunkStore, IngestResult


def make_indexer():
    return Indexer(store=ChunkStore())


class TestIngest:
    def test_ingest_is_idempotent(self):
        """同一 source_id 重复入库不产生重复 chunk"""
        idx = make_indexer()
        result1 = idx.ingest(source_id="kyoto-guide-01", content="京都攻略第一段\n京都攻略第二段", version=1)
        count1 = idx.count_chunks("kyoto-guide-01")

        result2 = idx.ingest(source_id="kyoto-guide-01", content="京都攻略第一段\n京都攻略第二段", version=1)
        count2 = idx.count_chunks("kyoto-guide-01")

        assert isinstance(result1, IngestResult)
        assert count1 == count2
        assert count1 == 2  # 两段 → 2 个 chunk

    def test_reingest_replaces_old_chunks(self):
        """攻略更新（version 递增）后旧 chunk 被替换，不残留"""
        idx = make_indexer()
        idx.ingest(source_id="kyoto-guide-01", content="旧版本内容第一段\n旧版本内容第二段", version=1)
        idx.ingest(source_id="kyoto-guide-01", content="新版本内容第一段\n新版本内容第二段\n新版本内容第三段", version=2)

        chunks = idx.get_chunks("kyoto-guide-01")
        assert len(chunks) == 3  # 只有新版本 chunk
        assert all(c.version == 2 for c in chunks)
        assert all("旧版本" not in c.text for c in chunks)

    def test_different_sources_are_isolated(self):
        idx = make_indexer()
        idx.ingest(source_id="kyoto-guide-01", content="京都攻略内容", version=1)
        idx.ingest(source_id="osaka-guide-01", content="大阪攻略内容", version=1)
        assert idx.count_chunks("kyoto-guide-01") == 1
        assert idx.count_chunks("osaka-guide-01") == 1
