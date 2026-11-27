import json

import pytest

from app.rag.index_versions import IndexVersionError, IndexVersionManager, resolve_index_path


def test_version_manager_activates_atomically_and_resolves_active_path(tmp_path):
    manager = IndexVersionManager(tmp_path / "indexes")
    version_path = manager.prepare_version("bge-v1")
    (version_path / "knowledge.manifest.json").write_text("{}", encoding="utf-8")

    manager.activate("bge-v1")

    assert manager.active_version() == "bge-v1"
    assert manager.resolve() == version_path
    pointer = json.loads(manager.pointer_path.read_text(encoding="utf-8"))
    assert pointer["active_version"] == "bge-v1"


def test_version_manager_rejects_path_traversal_and_missing_activation(tmp_path):
    manager = IndexVersionManager(tmp_path / "indexes")

    with pytest.raises(IndexVersionError):
        manager.version_path("../outside")
    with pytest.raises(IndexVersionError):
        manager.activate("missing")


def test_legacy_path_is_used_until_a_version_is_activated(tmp_path):
    root = tmp_path / "indexes"
    legacy = tmp_path / "legacy"
    legacy.mkdir()

    assert resolve_index_path(root, None, legacy) == legacy


def test_backup_copies_index_manifest_with_the_index(tmp_path):
    manager = IndexVersionManager(tmp_path / "indexes")
    source = manager.prepare_version("hash-v1")
    (source / "knowledge.manifest.json").write_text(
        '{"embedding":{"version":"hash-v1"}}',
        encoding="utf-8",
    )

    backup = manager.backup(source, tmp_path / "backups")

    assert backup is not None
    assert (backup / "knowledge.manifest.json").read_text(encoding="utf-8") == (
        '{"embedding":{"version":"hash-v1"}}'
    )
