"""Synchronize knowledge files into the local hybrid index.

Examples (run from ``backend``)::

    python scripts/ingest.py
    python scripts/ingest.py --file japan-kansai
    python scripts/ingest.py --dry-run
    python scripts/ingest.py --reset
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.chunking import CHUNKING_VERSION, split_document
from app.rag.chroma_store import ChromaIndexer
from app.core.config import BACKEND_ROOT, load_settings
from app.rag.embeddings import embedding_manifest
from app.rag.index_manifest import content_hash, load_manifest, save_manifest
from app.rag.index_versions import IndexVersionError, IndexVersionManager, resolve_index_path

KNOWLEDGE_ROOT = BACKEND_ROOT / "data" / "knowledge"
DEFAULT_PERSIST = str(BACKEND_ROOT / "chroma_data")


def source_id_from(path: Path) -> str:
    return path.stem


def plan_files(only: str | None = None) -> list[Path]:
    files = sorted(KNOWLEDGE_ROOT.rglob("*.md")) + sorted(KNOWLEDGE_ROOT.rglob("*.json"))
    if only:
        files = [file for file in files if only in str(file)]
    return files


def _ensure_unique_source_ids(files: list[Path]) -> None:
    grouped: dict[str, list[Path]] = {}
    for path in files:
        grouped.setdefault(source_id_from(path), []).append(path)
    collisions = {source_id: paths for source_id, paths in grouped.items() if len(paths) > 1}
    if collisions:
        details = "; ".join(
            f"{source_id}: {', '.join(str(path.relative_to(KNOWLEDGE_ROOT)) for path in paths)}"
            for source_id, paths in collisions.items()
        )
        raise SystemExit(f"source_id collision; rename one of these files: {details}")


def _relative_source_path(path: Path) -> str:
    return path.relative_to(KNOWLEDGE_ROOT).as_posix()


def main() -> None:
    parser = argparse.ArgumentParser(description="TravelMate knowledge index synchronizer")
    parser.add_argument("--file", type=str, default=None, help="only process paths containing this string")
    parser.add_argument("--dry-run", action="store_true", help="print the sync plan without writing")
    parser.add_argument("--reset", action="store_true", help="clear the selected index scope before syncing")
    parser.add_argument("--persist", type=str, default=None, help="legacy vector index directory")
    parser.add_argument("--index-root", type=str, default=None, help="versioned index root")
    parser.add_argument("--version", type=str, default=None, help="build an isolated index version")
    parser.add_argument("--activate", action="store_true", help="activate --version after a successful full sync")
    parser.add_argument("--collection", type=str, default="knowledge", help="collection name")
    args = parser.parse_args()

    settings = load_settings()
    configured_root_value = args.index_root or settings.travelmate_index_root
    configured_root = Path(configured_root_value) if configured_root_value else None
    if configured_root is not None and not configured_root.is_absolute():
        configured_root = BACKEND_ROOT / configured_root
    if args.version and configured_root is None:
        parser.error("--version requires --index-root or TRAVELMATE_INDEX_ROOT")
    if args.activate and (not args.version or args.file or args.dry_run):
        parser.error("--activate requires a full sync with --version")

    version_manager = IndexVersionManager(configured_root) if configured_root is not None else None
    if args.version and version_manager is not None:
        try:
            persist = version_manager.prepare_version(args.version, replace=args.reset)
        except IndexVersionError as exc:
            parser.error(str(exc))
    else:
        persist = Path(args.persist) if args.persist else resolve_index_path(
            configured_root,
            settings.travelmate_index_version or None,
            DEFAULT_PERSIST,
        )
    persist = persist.resolve()

    files = plan_files(args.file)
    _ensure_unique_source_ids(files)
    indexer = ChromaIndexer(persist_dir=str(persist), collection=args.collection)
    manifest = load_manifest(persist, args.collection)
    sources = dict(manifest.get("sources", {}))
    selected_source_ids = {source_id_from(path) for path in files}
    active_embedding = embedding_manifest(indexer.embedding_provider)
    index_health = indexer.health()

    stored_embedding = manifest.get("embedding")
    index_needs_rebuild = bool(indexer.count()) and (
        not isinstance(stored_embedding, dict)
        or stored_embedding != active_embedding
        or manifest.get("chunking_version") != CHUNKING_VERSION
        or not index_health.get("embedding_compatible", True)
    )
    if index_needs_rebuild and not args.file:
        if args.dry_run:
            print("检测到旧索引或 embedding/chunk 版本不一致，执行时将先重建整个索引")
        else:
            backup_root = Path(settings.travelmate_index_backup_root)
            if not backup_root.is_absolute():
                backup_root = BACKEND_ROOT.parent / backup_root
            backup_path = IndexVersionManager(BACKEND_ROOT).backup(persist, backup_root)
            if backup_path:
                print(f"已备份旧索引：{backup_path}")
            indexer.reset()
            sources = {}
            print("检测到旧索引或 embedding/chunk 版本不一致，已清空旧索引并开始重建")
    elif index_needs_rebuild and args.file and not args.reset and not args.dry_run:
        raise SystemExit(
            "selected sync cannot mix embedding versions; run without --file or add --reset to rebuild the index"
        )

    if args.reset and not args.dry_run:
        if args.file:
            for source_id in selected_source_ids:
                indexer.delete_source(source_id)
                sources.pop(source_id, None)
        else:
            indexer.reset()
            sources = {}
        print("已清理选定索引范围")

    print(f"发现 {len(files)} 个知识文件")
    total = 0
    changed = 0
    skipped = 0

    for path in files:
        source_id = source_id_from(path)
        content = path.read_text(encoding="utf-8")
        digest = content_hash(content)
        chunks = split_document(content, source_id, path.suffix)
        previous = sources.get(source_id, {})
        unchanged = (
            previous.get("content_hash") == digest
            and previous.get("chunking_version") == CHUNKING_VERSION
            and previous.get("embedding_model") == indexer.embedding_model
            and previous.get("embedding_version") == indexer.embedding_provider.version
            and previous.get("embedding_dimension") == indexer.embedding_dimension
            and indexer.exists(source_id)
        )

        if args.dry_run:
            state = "unchanged" if unchanged else "update"
            print(f"  [{source_id}] {len(chunks)} chunks ({state}, sha256:{digest[:12]})")
        elif unchanged:
            skipped += 1
            print(f"  [{source_id}] 未变化，跳过 embedding ({len(chunks)} chunks)")
        else:
            result = indexer.ingest(
                source_id=source_id,
                content=content,
                version=1,
                chunks=chunks,
                source_path=_relative_source_path(path),
                content_hash=digest,
            )
            sources[source_id] = {
                "path": _relative_source_path(path),
                "content_hash": digest,
                "chunk_count": result.chunk_count,
                "chunking_version": CHUNKING_VERSION,
                "embedding_model": indexer.embedding_model,
                "embedding_version": indexer.embedding_provider.version,
                "embedding_dimension": indexer.embedding_dimension,
            }
            changed += 1
            print(f"  [{source_id}] 已更新 {result.chunk_count} chunks (sha256:{digest[:12]})")
        total += len(chunks)

    if not args.dry_run:
        if not args.file:
            removed = set(sources) - selected_source_ids
            for source_id in removed:
                indexer.delete_source(source_id)
                sources.pop(source_id, None)
                print(f"  [{source_id}] 已删除过期 source")

        save_manifest(
            persist,
            args.collection,
            {
                "collection": args.collection,
                "chunking_version": CHUNKING_VERSION,
                "embedding": active_embedding,
                "sources": sources,
            },
        )
        if args.activate and version_manager is not None and args.version:
            version_manager.activate(args.version)
            print(f"已激活索引版本：{args.version}")

    suffix = "（dry-run，未写库）" if args.dry_run else f"（更新 {changed}，跳过 {skipped}）"
    print(f"索引目录：{persist}")
    print(f"合计 {total} chunks {suffix}")


if __name__ == "__main__":
    main()
