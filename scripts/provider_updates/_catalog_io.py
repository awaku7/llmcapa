"""Shared JSON file I/O conventions for provider catalog updater scripts."""

from __future__ import annotations

import json
from os import PathLike
from pathlib import Path
from typing import Any


def load_json(path: str | PathLike[str]) -> Any:
    """Load UTF-8 JSON from a path."""
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def serialize_json(value: Any) -> str:
    """Return compact, Unicode-preserving JSON with one trailing newline."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"


def save_json(path: str | PathLike[str], value: Any) -> None:
    """Write compact, Unicode-preserving UTF-8 JSON with a final newline."""
    Path(path).write_bytes(serialize_json(value).encode("utf-8"))


def compact_json_file(path: str | PathLike[str]) -> None:
    """Compact an existing JSON file without changing its parsed value."""
    target = Path(path)
    compact = serialize_json(load_json(target)).encode("utf-8")
    if target.read_bytes() != compact:
        target.write_bytes(compact)
