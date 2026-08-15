"""retriever 边界行为测试（RED 阶段，对应缺陷 H2）"""
from app.rag.retriever import Retriever, Document


class TestRetriever:
    def test_empty_db_returns_no_citations(self):
        """空库查询返回空列表，不抛异常"""
        r = Retriever(docs=[])
        assert r.search("冰岛", top_k=5) == []

    def test_low_relevance_is_rejected(self):
        """相关度低于 min_score 的结果不放行"""
        r = Retriever(
            docs=[Document(source_id="a", text="量子物理入门", score=0.05)],
            min_score=0.3,
        )
        assert r.search("冰岛旅行", top_k=5) == []

    def test_top_k_ordering(self):
        """结果按相关度降序返回，且数量不超过 top_k"""
        docs = [
            Document(source_id="c", text="冰岛极光攻略", score=0.6),
            Document(source_id="a", text="冰岛自驾环岛", score=0.9),
            Document(source_id="b", text="冰岛签证指南", score=0.4),
        ]
        r = Retriever(docs=docs, min_score=0.3)
        result = r.search("冰岛自驾", top_k=2)
        assert [d.source_id for d in result] == ["a", "c"]

    def test_all_results_above_threshold(self):
        """任意返回结果的 score 都 >= min_score"""
        docs = [
            Document(source_id="a", text="日本关西攻略", score=0.85),
            Document(source_id="b", text="日本签证材料", score=0.55),
            Document(source_id="c", text="数学论文", score=0.1),
        ]
        r = Retriever(docs=docs, min_score=0.3)
        result = r.search("日本旅行", top_k=5)
        assert all(d.score >= 0.3 for d in result)
        assert "c" not in [d.source_id for d in result]

    def test_citation_source_must_exist(self):
        """citation 的 source_id 必须存在于库中（引用完整性）"""
        docs = [
            Document(source_id="kyoto-guide-01", text="京都攻略", score=0.9),
        ]
        r = Retriever(docs=docs, min_score=0.3)
        result = r.search("京都", top_k=5)
        assert all(d.source_id in {"kyoto-guide-01"} for d in result)
