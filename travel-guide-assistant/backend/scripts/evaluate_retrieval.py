"""Evaluate retrieval against the checked-in golden question set.

Run from the backend directory:

    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --top-k 5 --report docs/retrieval.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Iterable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import BACKEND_ROOT, load_settings
from app.rag.chroma_store import ChromaRetriever
from app.rag.index_versions import resolve_index_path

DEFAULT_GOLDEN = BACKEND_ROOT / "tests" / "golden_qa.json"
DEFAULT_PERSIST = BACKEND_ROOT / "chroma_data"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_pairs(path: str | Path = DEFAULT_GOLDEN) -> list[dict[str, Any]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = value.get("pairs") if isinstance(value, dict) else None
    if not isinstance(pairs, list):
        raise ValueError(f"golden file has no pairs list: {path}")
    return [pair for pair in pairs if isinstance(pair, dict) and pair.get("question")]


def evaluate_retrieval(
    retriever: ChromaRetriever,
    pairs: Iterable[dict[str, Any]],
    cutoffs: tuple[int, ...] = (1, 3, 5),
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    pairs = list(pairs)
    max_cutoff = max(cutoffs, default=5)

    for pair in pairs:
        started = time.perf_counter()
        documents = retriever.search(pair["question"], top_k=max_cutoff)
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies.append(elapsed_ms)
        sources = [document.source_id for document in documents]
        expected = set(pair.get("expected_sources") or [])
        first_rank = next(
            (rank for rank, source_id in enumerate(sources, start=1) if source_id in expected),
            None,
        )
        rows.append(
            {
                "id": pair.get("id"),
                "question": pair["question"],
                "expected_sources": sorted(expected),
                "sources": sources,
                "scores": [round(float(document.score), 6) for document in documents],
                "first_relevant_rank": first_rank,
                "latency_ms": round(elapsed_ms, 3),
                "hit": {
                    str(cutoff): any(source in expected for source in sources[:cutoff])
                    for cutoff in cutoffs
                },
            }
        )

    denominator = len(rows) or 1
    recall = {
        f"recall_at_{cutoff}": round(
            sum(row["hit"][str(cutoff)] for row in rows) / denominator,
            4,
        )
        for cutoff in cutoffs
    }
    reciprocal_ranks = [
        1 / row["first_relevant_rank"]
        for row in rows
        if row["first_relevant_rank"] is not None
    ]
    retrieved = sum(len(row["sources"]) for row in rows)
    relevant = sum(
        sum(source in set(row["expected_sources"]) for source in row["sources"])
        for row in rows
    )
    precision_at = {
        f"precision_at_{cutoff}": round(
            sum(
                sum(source in set(row["expected_sources"]) for source in row["sources"][:cutoff])
                / max(1, len(row["sources"][:cutoff]))
                for row in rows
            )
            / denominator,
            4,
        )
        for cutoff in cutoffs
    }
    return {
        "query_count": len(rows),
        **recall,
        "mrr": round(sum(reciprocal_ranks) / denominator, 4),
        "source_precision": round(relevant / retrieved, 4) if retrieved else 0.0,
        **precision_at,
        "latency_ms": {
            "mean": round(statistics.mean(latencies), 3) if latencies else 0.0,
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
        },
        "rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--persist", type=Path)
    parser.add_argument("--collection", default="knowledge")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--min-score", type=float)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--require-recall-at-3", type=float)
    parser.add_argument("--require-recall-at-5", type=float)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    settings = load_settings()
    configured_root = Path(settings.travelmate_index_root) if settings.travelmate_index_root else None
    if configured_root is not None and not configured_root.is_absolute():
        configured_root = BACKEND_ROOT / configured_root
    persist = args.persist or resolve_index_path(
        configured_root,
        settings.travelmate_index_version or None,
        DEFAULT_PERSIST,
    )
    retriever = ChromaRetriever(
        persist_dir=str(persist),
        collection=args.collection,
        min_score=args.min_score if args.min_score is not None else settings.travelmate_retrieval_min_score,
    )
    result = {
        "persist": str(persist),
        "collection": args.collection,
        "embedding_model": retriever.embedding_model,
        "embedding_dimension": retriever.embedding_dimension,
        "index": retriever.health(),
        "evaluation": evaluate_retrieval(
            retriever,
            load_pairs(args.golden),
            cutoffs=tuple(sorted({1, 3, min(args.top_k, 5)})),
        ),
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered + "\n", encoding="utf-8")
    failures = []
    if args.require_recall_at_3 is not None and result["evaluation"].get("recall_at_3", 0.0) < args.require_recall_at_3:
        failures.append(
            f"Recall@3 {result['evaluation'].get('recall_at_3', 0.0):.4f} < {args.require_recall_at_3:.4f}"
        )
    if args.require_recall_at_5 is not None and result["evaluation"].get("recall_at_5", 0.0) < args.require_recall_at_5:
        failures.append(
            f"Recall@5 {result['evaluation'].get('recall_at_5', 0.0):.4f} < {args.require_recall_at_5:.4f}"
        )
    if failures:
        print("Retrieval quality gate failed: " + "; ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
