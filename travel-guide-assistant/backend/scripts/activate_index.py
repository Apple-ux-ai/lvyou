"""Activate an already-built versioned index after external quality gates pass."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.rag.index_versions import IndexVersionManager


def main() -> None:
    parser = argparse.ArgumentParser(description="Activate a TravelMate index version")
    parser.add_argument("--index-root", required=True, type=Path)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()

    index_root = args.index_root
    if not index_root.is_absolute():
        index_root = BACKEND_ROOT / index_root
    activated = IndexVersionManager(index_root.resolve()).activate(args.version)
    print(f"已激活索引版本：{args.version}")
    print(f"索引目录：{activated}")


if __name__ == "__main__":
    main()
