from app.rag.chroma_store import ChromaIndexer, ChromaRetriever
from app.rag.embeddings import HashEmbedding


class CountingEmbedding:
    model_id = "counting"
    dimension = 2

    def __init__(self, version="v1"):
        self.version = version
        self.document_calls = 0

    def embed_documents(self, texts):
        self.document_calls += 1
        return [[1.0, 0.0] if "京都" in text else [0.0, 1.0] for text in texts]

    def embed_query(self, text):
        return [1.0, 0.0] if "京都" in text else [0.0, 1.0]

    def __call__(self, texts):
        return self.embed_documents(texts)


def test_hybrid_retrieval_prefers_exact_entity_and_deduplicates_sources(tmp_path):
    provider = HashEmbedding(dimension=128)
    indexer = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=provider,
    )
    indexer.ingest(
        "bangkok-guide",
        "曼谷 BTS 和 MRT 适合市内出行。\n曼谷大皇宫与郑王庙值得参观。",
        version=1,
    )
    indexer.ingest("kyoto-guide", "京都巴士和地铁覆盖主要景点。", version=1)

    retriever = ChromaRetriever(
        persist_dir=str(tmp_path),
        collection="knowledge",
        min_score=0.01,
        embedding_fn=provider,
    )
    results = retriever.search("曼谷 BTS MRT", top_k=3)

    assert results
    assert results[0].source_id == "bangkok-guide"
    assert len({result.source_id for result in results}) == len(results)


def test_document_embeddings_are_reused_across_indexer_instances(tmp_path):
    first_provider = CountingEmbedding()
    first = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=first_provider,
    )
    first.ingest("kyoto-guide", "京都交通\n京都景点", version=1)
    assert first_provider.document_calls == 1

    second_provider = CountingEmbedding()
    second = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=second_provider,
    )
    second.ingest("kyoto-guide", "京都交通\n京都景点", version=1)
    assert second_provider.document_calls == 0

    changed_provider = CountingEmbedding(version="v2")
    changed = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=changed_provider,
    )
    changed.ingest("kyoto-guide", "京都交通\n京都景点", version=1)
    assert changed_provider.document_calls == 1


def test_large_json_fallback_keeps_records_in_memory_between_queries(tmp_path):
    provider = HashEmbedding(dimension=64)
    indexer = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=provider,
    )
    content = "\n".join(f"京都景点说明 {index}" for index in range(1000))
    indexer.ingest("large-guide", content, version=1)

    retriever = ChromaRetriever(
        persist_dir=str(tmp_path),
        collection="knowledge",
        min_score=0.0,
        embedding_fn=provider,
    )
    retriever.search("京都景点", top_k=5)
    records = retriever._fallback_store._records
    mtime = retriever._fallback_store._mtime_ns
    retriever.search("京都景点 999", top_k=5)

    assert retriever._fallback_store._records is records
    assert retriever._fallback_store._mtime_ns == mtime
