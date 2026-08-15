from app.rag.retriever import Document
from scripts.evaluate_retrieval import evaluate_retrieval


class FakeRetriever:
    embedding_model = "test"

    def search(self, query, top_k=5):
        return [
            Document(source_id="expected", text=query, score=0.9),
            Document(source_id="other", text="other", score=0.1),
        ][:top_k]


def test_evaluation_reports_recall_mrr_and_latency_fields():
    result = evaluate_retrieval(
        FakeRetriever(),
        [{"id": "qa-1", "question": "京都", "expected_sources": ["expected"]}],
    )

    assert result["recall_at_1"] == 1.0
    assert result["recall_at_3"] == 1.0
    assert result["mrr"] == 1.0
    assert result["latency_ms"]["p95"] >= 0
