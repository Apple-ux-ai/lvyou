from app.rag.chroma_store import ChromaIndexer, ChromaRetriever
from app.rag.embeddings import HashEmbedding


def test_mismatched_embedding_dimensions_are_reported_without_mixing_vectors(tmp_path):
    indexer = ChromaIndexer(
        persist_dir=str(tmp_path),
        collection="knowledge",
        embedding_fn=HashEmbedding(dimension=8, version="hash-v1"),
    )
    indexer.ingest("kyoto", "京都交通", version=1)

    retriever = ChromaRetriever(
        persist_dir=str(tmp_path),
        collection="knowledge",
        min_score=0.0,
        embedding_fn=HashEmbedding(dimension=16, version="hash-v2"),
    )

    health = retriever.health()
    assert health["stored_dimensions"] == [8]
    assert health["embedding_compatible"] is False
