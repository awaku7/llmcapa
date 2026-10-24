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


def save_json(path: str | PathLike[str], value: Any) -> None:
    """Write pretty, Unicode-preserving UTF-8 JSON with a final newline."""
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    Path(path).write_text(text, encoding="utf-8")
