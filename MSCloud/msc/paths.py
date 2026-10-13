"""Filesystem paths for project and user data."""

from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def credentials_path() -> Path:
    return project_root() / "credentials.json"


def app_data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if base:
        path = Path(base) / "MSCloud"
    else:
        path = Path.home() / ".mscloud"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path() -> Path:
    return app_data_dir() / "msc.sqlite"


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    """Reserved for future offline cache."""
    path = app_data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_destination(base_dir: Path, filename: str) -> Path:
    """Resolve a file path under base_dir; reject path traversal."""
    base = base_dir.resolve()
    dest = (base / filename).resolve()
    if dest != base and base not in dest.parents:
        raise ValueError("Invalid download path")
    return dest
