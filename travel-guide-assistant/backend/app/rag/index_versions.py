"""Versioned index directories and an atomic active-version pointer."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class IndexVersionError(ValueError):
    """Raised when an index version is invalid or cannot be activated."""


class IndexVersionManager:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.versions_dir = self.root / "versions"
        self.pointer_path = self.root / "active.json"

    @staticmethod
    def validate_version(version: str) -> str:
        if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
            raise IndexVersionError(
                "index version must contain 1-64 letters, numbers, dots, underscores, or hyphens"
            )
        return version

    def version_path(self, version: str) -> Path:
        return self.versions_dir / self.validate_version(version)

    def active_version(self) -> str | None:
        if not self.pointer_path.exists():
            return None
        try:
            value = json.loads(self.pointer_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        version = value.get("active_version") if isinstance(value, dict) else None
        return version if isinstance(version, str) and VERSION_PATTERN.fullmatch(version) else None

    def resolve(self, requested_version: str | None = None, legacy_path: Path | None = None) -> Path:
        if requested_version:
            path = self.version_path(requested_version)
            if not path.exists():
                raise IndexVersionError(f"index version does not exist: {requested_version}")
            return path
        active = self.active_version()
        if active:
            path = self.version_path(active)
            if path.exists():
                return path
        if legacy_path is not None and legacy_path.exists():
            return legacy_path
        return self.root

    def prepare_version(self, version: str, *, replace: bool = False) -> Path:
        path = self.version_path(version)
        if path.exists() and any(path.iterdir()) and not replace:
            raise IndexVersionError(f"index version already contains data: {version}")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def activate(self, version: str) -> Path:
        path = self.version_path(version)
        if not path.exists():
            raise IndexVersionError(f"cannot activate missing index version: {version}")
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "active_version": self.validate_version(version),
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "relative_path": str(path.relative_to(self.root)).replace("\\", "/"),
        }
        temporary = self.pointer_path.with_suffix(self.pointer_path.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.pointer_path)
        return path

    def backup(self, source_path: str | Path, backup_root: str | Path) -> Path | None:
        source = Path(source_path)
        if not source.exists():
            return None
        backup_root = Path(backup_root)
        backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = backup_root / f"index-{stamp}"
        suffix = 1
        while target.exists():
            target = backup_root / f"index-{stamp}-{suffix}"
            suffix += 1
        shutil.copytree(source, target)
        return target


def resolve_index_path(
    root: str | Path | None,
    requested_version: str | None,
    legacy_path: str | Path,
) -> Path:
    """Resolve configured versioned storage while preserving legacy installs."""
    legacy = Path(legacy_path)
    if not root:
        return legacy
    return IndexVersionManager(root).resolve(requested_version, legacy)

