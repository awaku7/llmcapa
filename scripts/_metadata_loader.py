"""Load provider metadata overrides from JSON, not Python source literals."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
METADATA = ROOT / "metadata"


@lru_cache(maxsize=None)
def load_overrides(name: str) -> dict[tuple[str, str], dict[str, Any]]:
    """Load ``provider::model_id`` metadata overrides from a JSON file."""
    path = METADATA / name
    data = json.loads(path.read_text(encoding="utf-8"))
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for key, value in data.items():
        provider, separator, model_id = key.partition("::")
        if not separator or not provider or not model_id or not isinstance(value, dict):
            raise ValueError(f"Invalid override key/value in {path}: {key!r}")
        result[(provider, model_id)] = value
    return result
