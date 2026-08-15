from app.rag.index_manifest import content_hash, inspect_manifest, load_manifest, save_manifest


def test_manifest_round_trip_is_atomic_and_content_hash_is_stable(tmp_path):
    value = {"collection": "knowledge", "sources": {"kyoto": {"chunk_count": 2}}}

    saved = save_manifest(tmp_path, "knowledge", value)
    loaded = load_manifest(tmp_path, "knowledge")

    assert saved.name == "knowledge.manifest.json"
    assert loaded["manifest_version"] == 1
    assert loaded["sources"]["kyoto"]["chunk_count"] == 2
    assert content_hash("same") == content_hash("same")
    assert content_hash("same") != content_hash("changed")


def test_manifest_inspection_detects_source_and_embedding_drift(tmp_path):
    embedding = {"model_id": "hash-ngram-v2", "version": "v2", "dimension": 8}
    save_manifest(
        tmp_path,
        "knowledge",
        {
            "chunking_version": "chunk-v1",
            "embedding": embedding,
            "sources": {"kyoto": {"chunk_count": 2}},
        },
    )

    compatible = inspect_manifest(
        tmp_path,
        "knowledge",
        embedding=embedding,
        chunking_version="chunk-v1",
        source_ids={"kyoto"},
        chunk_count=2,
    )
    drifted = inspect_manifest(
        tmp_path,
        "knowledge",
        embedding={**embedding, "version": "v3"},
        chunking_version="chunk-v1",
        source_ids={"kyoto", "osaka"},
        chunk_count=3,
    )

    assert compatible["compatible"] is True
    assert drifted["compatible"] is False
    assert drifted["status"] == "mismatch"
