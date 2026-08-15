"""Chroma 向量检索集成测试（RED 阶段）

使用真实 Chroma（临时目录 + 默认 embedding 模型），验证：
- 入库后可被语义检索命中
- 空库返回空
- 相关度阈值过滤
- 幂等：重复入库不产生重复 chunk
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from app.rag.chroma_store import ChromaIndexer, ChromaRetriever


@pytest.fixture()
def chroma_path(tmp_path):
    """每个测试独立临时目录，避免相互污染"""
    path = tmp_path / "chroma_test"
    yield str(path)
    shutil.rmtree(path, ignore_errors=True)


class TestChromaIndexer:
    def test_ingest_then_retrieve(self, chroma_path):
        """入库后语义检索能命中相关内容"""
        indexer = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        indexer.ingest(source_id="kyoto-guide", content="京都的伏见稻荷大社以千本鸟居闻名，春季樱花季人最多。岚山的竹林小径非常幽静。", version=1)

        retriever = ChromaRetriever(persist_dir=chroma_path, collection="guides", min_score=0.02)
        results = retriever.search("京都赏樱", top_k=3)
        assert len(results) >= 1
        assert any(d.source_id == "kyoto-guide" for d in results)

    def test_empty_collection_returns_empty(self, chroma_path):
        """空集合查询返回空列表，不抛异常"""
        retriever = ChromaRetriever(persist_dir=chroma_path, collection="guides", min_score=0.02)
        assert retriever.search("冰岛极光", top_k=5) == []

    def test_ingest_is_idempotent(self, chroma_path):
        """同一 source_id + version 重复入库不产生重复 chunk"""
        indexer = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        indexer.ingest(source_id="iceland-guide", content="冰岛冬季可以看极光，蓝冰洞在杰古沙龙冰河湖。", version=1)
        count1 = indexer.count_chunks("iceland-guide")
        indexer.ingest(source_id="iceland-guide", content="冰岛冬季可以看极光，蓝冰洞在杰古沙龙冰河湖。", version=1)
        count2 = indexer.count_chunks("iceland-guide")
        assert count1 == count2
        assert count1 == 1

    def test_reingest_replaces_old_version(self, chroma_path):
        """version 递增后旧 chunk 被替换，不残留"""
        indexer = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        indexer.ingest(source_id="dali-guide", content="大理洱海环湖骑行，苍山云海日出。", version=1)
        indexer.ingest(
            source_id="dali-guide",
            content="大理洱海环湖骑行，苍山云海日出。\n喜洲古镇白族建筑。",
            version=2,
        )
        chunks = indexer.get_chunks("dali-guide")
        assert len(chunks) == 2  # 新版本 2 行 → 2 个 chunk
        assert all(c.version == 2 for c in chunks)
        assert all("喜洲" in c.text or "洱海" in c.text for c in chunks)


class TestChromaRetriever:
    def test_low_relevance_is_filtered(self, chroma_path):
        """无关查询低于 min_score 时返回空"""
        indexer = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        indexer.ingest(source_id="kyoto-guide", content="京都伏见稻荷、岚山竹林、金阁寺。", version=1)
        retriever = ChromaRetriever(persist_dir=chroma_path, collection="guides", min_score=0.2)
        # 高度无关的查询应低于阈值
        results = retriever.search("量子物理与相对论", top_k=3)
        assert results == []

    def test_top_k_ordering(self, chroma_path):
        """返回结果按相关度降序，数量不超过 top_k"""
        indexer = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        indexer.ingest(source_id="a", content="冰岛极光自驾攻略 蓝冰洞", version=1)
        indexer.ingest(source_id="b", content="京都樱花美食攻略", version=1)
        indexer.ingest(source_id="c", content="大理洱海骑行", version=1)
        retriever = ChromaRetriever(persist_dir=chroma_path, collection="guides", min_score=0.02)
        results = retriever.search("冰岛看极光", top_k=2)
        assert len(results) <= 2
        scores = [d.score for d in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0].source_id == "a"

    def test_different_collections_are_isolated(self, chroma_path):
        """不同集合互不影响"""
        i1 = ChromaIndexer(persist_dir=chroma_path, collection="guides")
        i2 = ChromaIndexer(persist_dir=chroma_path, collection="pois")
        i1.ingest(source_id="x", content="京都攻略内容", version=1)
        i2.ingest(source_id="x", content="京都景点 POI", version=1)
        assert i1.count_chunks("x") == 1
        assert i2.count_chunks("x") == 1
