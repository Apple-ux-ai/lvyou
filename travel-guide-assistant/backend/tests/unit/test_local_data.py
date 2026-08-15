import json
import sqlite3

import pytest

from scripts.local_data import BackupError, create_backup, restore_backup, verify_backup


def write_trip_database(path, destination):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE trips (destination TEXT NOT NULL)")
    connection.execute("INSERT INTO trips (destination) VALUES (?)", (destination,))
    connection.commit()
    connection.close()


def read_destination(path):
    connection = sqlite3.connect(path)
    value = connection.execute("SELECT destination FROM trips").fetchone()[0]
    connection.close()
    return value


def test_create_backup_copies_sqlite_and_chroma(tmp_path):
    project_root = tmp_path / "project"
    write_trip_database(project_root / "backend/data/trips.db", "Kyoto")
    chroma_file = project_root / "backend/chroma_data/index.bin"
    chroma_file.parent.mkdir(parents=True)
    chroma_file.write_bytes(b"vector-index")
    (chroma_file.parent / "knowledge.manifest.json").write_text(
        json.dumps(
            {
                "embedding": {"provider": "hash", "model": "hash-ngram-v2"},
                "chunking_version": "chunk-v2",
                "sources": {"kyoto": {"chunk_count": 1}},
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "backup"

    result = create_backup(project_root, destination, timestamp="20260808-101500")

    assert result == destination
    verification = verify_backup(result)
    assert verification["trips_db"]["integrity"] == "ok"
    assert verification["legacy_index"]["source_count"] == 1
    assert read_destination(destination / "trips.db") == "Kyoto"
    assert (destination / "chroma_data/index.bin").read_bytes() == b"vector-index"
    manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["version"] == 1
    assert manifest["contains"] == {"trips_db": True, "chroma_data": True}
    assert manifest["index"]["manifest_path"] == "chroma_data/knowledge.manifest.json"
    assert manifest["index"]["source_count"] == 1


def test_restore_replaces_data_and_creates_safety_snapshot(tmp_path):
    source_root = tmp_path / "source"
    write_trip_database(source_root / "backend/data/trips.db", "Kyoto")
    source_chroma = source_root / "backend/chroma_data/index.bin"
    source_chroma.parent.mkdir(parents=True)
    source_chroma.write_bytes(b"old-index")
    backup_path = create_backup(source_root, tmp_path / "backup", timestamp="20260808-101500")

    project_root = tmp_path / "project"
    write_trip_database(project_root / "backend/data/trips.db", "Osaka")
    current_chroma = project_root / "backend/chroma_data/index.bin"
    current_chroma.parent.mkdir(parents=True)
    current_chroma.write_bytes(b"current-index")

    safety_path = restore_backup(project_root, backup_path, timestamp="20260808-102000")

    assert read_destination(project_root / "backend/data/trips.db") == "Kyoto"
    assert current_chroma.read_bytes() == b"old-index"
    assert safety_path == project_root / ".local/pre-restore/20260808-102000"
    assert read_destination(safety_path / "trips.db") == "Osaka"
    assert (safety_path / "chroma_data/index.bin").read_bytes() == b"current-index"


def test_restore_rejects_directory_without_manifest(tmp_path):
    backup_path = tmp_path / "invalid-backup"
    backup_path.mkdir()

    with pytest.raises(BackupError, match="manifest"):
        restore_backup(tmp_path / "project", backup_path)


def test_backup_and_restore_preserve_versioned_index(tmp_path):
    source_root = tmp_path / "source"
    write_trip_database(source_root / "backend/data/trips.db", "Kyoto")
    index_root = source_root / "backend/index_versions"
    active_version = index_root / "versions/bge-v1"
    active_version.mkdir(parents=True)
    (index_root / "active.json").write_text(
        json.dumps({"active_version": "bge-v1"}),
        encoding="utf-8",
    )
    (active_version / "knowledge.manifest.json").write_text(
        json.dumps(
            {
                "embedding": {"model_id": "bge-small-zh-v1.5", "dimension": 512},
                "chunking_version": "section-v1",
                "sources": {"kyoto": {"chunk_count": 2}},
            }
        ),
        encoding="utf-8",
    )

    backup_path = create_backup(source_root, tmp_path / "backup", timestamp="20260808-103000")
    backup_manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    verification = verify_backup(backup_path)

    assert backup_manifest["contains"]["index_versions"] is True
    assert backup_manifest["index"]["versioned_index"]["active_version"] == "bge-v1"
    assert verification["versioned_index"]["active_version"] == "bge-v1"
    assert (backup_path / "index_versions/active.json").is_file()

    project_root = tmp_path / "project"
    write_trip_database(project_root / "backend/data/trips.db", "Osaka")
    current_index = project_root / "backend/index_versions/versions/hash-v1"
    current_index.mkdir(parents=True)
    (project_root / "backend/index_versions/active.json").write_text(
        json.dumps({"active_version": "hash-v1"}),
        encoding="utf-8",
    )
    (current_index / "knowledge.manifest.json").write_text("{}", encoding="utf-8")

    safety_path = restore_backup(project_root, backup_path, timestamp="20260808-103100")

    restored_pointer = json.loads(
        (project_root / "backend/index_versions/active.json").read_text(encoding="utf-8")
    )
    assert restored_pointer["active_version"] == "bge-v1"
    assert (project_root / "backend/index_versions/versions/bge-v1/knowledge.manifest.json").is_file()
    safety_pointer = json.loads(
        (safety_path / "index_versions/active.json").read_text(encoding="utf-8")
    )
    assert safety_pointer["active_version"] == "hash-v1"


def test_verify_backup_rejects_missing_active_version_manifest(tmp_path):
    project_root = tmp_path / "project"
    index_root = project_root / "backend/index_versions"
    (index_root / "versions/bge-v1").mkdir(parents=True)
    (index_root / "active.json").write_text(
        json.dumps({"active_version": "bge-v1"}),
        encoding="utf-8",
    )
    (index_root / "versions/bge-v1/knowledge.manifest.json").write_text("{}", encoding="utf-8")
    backup_path = create_backup(project_root, tmp_path / "backup", timestamp="20260808-104000")

    (backup_path / "index_versions/active.json").write_text(
        json.dumps({"active_version": "missing"}),
        encoding="utf-8",
    )

    with pytest.raises(BackupError, match="missing manifest"):
        verify_backup(backup_path)
