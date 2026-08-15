import json
import sys

import pytest

from app.rag import index_manifest
from app.rag.chroma_store import ChromaIndexer
from app.rag.index_versions import IndexVersionManager
import scripts.ingest as ingest


def _run_ingest(monkeypatch, knowledge_root, persist, *extra_args):
    monkeypatch.setattr(ingest, "KNOWLEDGE_ROOT", knowledge_root)
    monkeypatch.setattr(
        sys,
        "argv",
        ["ingest.py", "--persist", str(persist), *extra_args],
    )
    ingest.main()


def test_sync_add_modify_delete_and_restore_sources(monkeypatch, tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "guides").mkdir(parents=True)
    (knowledge / "guides" / "kyoto.md").write_text("# 京都\n交通建议", encoding="utf-8")
    (knowledge / "guides" / "dali.md").write_text("# 大理\n洱海骑行", encoding="utf-8")
    persist = tmp_path / "index"

    _run_ingest(monkeypatch, knowledge, persist)
    first = index_manifest.load_manifest(persist, "knowledge")
    assert set(first["sources"]) == {"kyoto", "dali"}

    (knowledge / "guides" / "kyoto.md").write_text("# 京都\n机场到市区交通", encoding="utf-8")
    (knowledge / "guides" / "dali.md").unlink()
    (knowledge / "guides" / "bangkok.md").write_text("# 曼谷\nBTS 出行", encoding="utf-8")
    _run_ingest(monkeypatch, knowledge, persist)

    second = index_manifest.load_manifest(persist, "knowledge")
    indexer = ChromaIndexer(persist_dir=str(persist), collection="knowledge")
    assert set(second["sources"]) == {"kyoto", "bangkok"}
    assert indexer.source_ids() == {"kyoto", "bangkok"}
    assert "机场到市区交通" in indexer.get_chunks("kyoto")[0].text

    (knowledge / "guides" / "dali.md").write_text("# 大理\n苍山日出", encoding="utf-8")
    _run_ingest(monkeypatch, knowledge, persist)
    restored = index_manifest.load_manifest(persist, "knowledge")
    assert set(restored["sources"]) == {"kyoto", "dali", "bangkok"}


def test_sync_rejects_duplicate_source_ids(monkeypatch, tmp_path):
    knowledge = tmp_path / "knowledge"
    (knowledge / "one").mkdir(parents=True)
    (knowledge / "two").mkdir(parents=True)
    (knowledge / "one" / "same.md").write_text("# same\nA", encoding="utf-8")
    (knowledge / "two" / "same.json").write_text(json.dumps({"title": "same"}), encoding="utf-8")

    with pytest.raises(SystemExit, match="source_id collision"):
        _run_ingest(monkeypatch, knowledge, tmp_path / "index")


def test_full_sync_can_build_and_activate_an_isolated_version(monkeypatch, tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "kyoto.md").write_text("# 京都\n交通", encoding="utf-8")
    index_root = tmp_path / "versions"
    monkeypatch.setattr(ingest, "KNOWLEDGE_ROOT", knowledge)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest.py",
            "--index-root",
            str(index_root),
            "--version",
            "hash-v1",
            "--activate",
        ],
    )

    ingest.main()

    manager = IndexVersionManager(index_root)
    assert manager.active_version() == "hash-v1"
    assert manager.resolve().exists()
