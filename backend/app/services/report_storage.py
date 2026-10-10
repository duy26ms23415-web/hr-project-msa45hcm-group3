"""Private, atomic storage for generated report files and preview snapshots."""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.config import settings


REPORT_KEY_RE = re.compile(r"^[a-f0-9]{32}\.(xlsx|json)$")


def resolve_report_path(storage_key: str) -> Path:
    if not REPORT_KEY_RE.fullmatch(storage_key):
        raise FileNotFoundError("Invalid report storage key")
    root = Path(settings.REPORT_STORAGE_DIR).expanduser().resolve()
    candidate = (root / storage_key).resolve()
    if candidate.parent != root:
        raise FileNotFoundError("Invalid report storage key")
    return candidate


def store_report(data: bytes, extension: str) -> tuple[str, str]:
    if extension not in {"xlsx", "json"} or not data:
        raise ValueError("Invalid report artifact")
    root = Path(settings.REPORT_STORAGE_DIR).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    key = f"{uuid4().hex}.{extension}"
    destination = resolve_report_path(key)
    descriptor, staging = tempfile.mkstemp(prefix=".staging-", suffix=f".{extension}", dir=root)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staging, destination)
    except Exception:
        try:
            os.unlink(staging)
        except FileNotFoundError:
            pass
        raise
    return key, hashlib.sha256(data).hexdigest()


def delete_report(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        resolve_report_path(storage_key).unlink()
    except FileNotFoundError:
        pass


def orphan_report_keys(referenced_keys: set[str], now: datetime | None = None) -> list[str]:
    """Find only server-format artifacts older than twice the run TTL."""
    root = Path(settings.REPORT_STORAGE_DIR).expanduser().resolve()
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=2)).timestamp()
    if not root.is_dir():
        return []
    candidates = []
    for candidate in root.iterdir():
        if candidate.name in referenced_keys or not REPORT_KEY_RE.fullmatch(candidate.name) or candidate.is_symlink():
            continue
        try:
            path = resolve_report_path(candidate.name)
            if path.is_file() and path.stat().st_mtime < cutoff:
                candidates.append(candidate.name)
        except FileNotFoundError:
            continue
    return candidates
