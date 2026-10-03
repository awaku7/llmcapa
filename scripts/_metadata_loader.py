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


def context_window_override(provider: str, model_id: str) -> dict[str, Any] | None:
    """Return a documented context-window fallback from metadata JSON."""
    return load_overrides("context_window_overrides.json").get((provider, model_id))


def apply_context_window_overrides(models: list[dict[str, Any]]) -> int:
    """Fill unknown context windows from cited provider metadata fallbacks.

    Live values already present on a row take precedence. The fallback values
    live in scripts/metadata/context_window_overrides.json, not updater code.
    """
    applied = 0
    for model in models:
        provider = str(model.get("provider", ""))
        model_id = str(model.get("model_id", ""))
        override = context_window_override(provider, model_id)
        if not override:
            continue
        try:
            current_value = int(model.get("context_window") or 0)
        except (TypeError, ValueError):
            current_value = 0
        if current_value > 0:
            continue
        value = override.get("context_window")
        if not isinstance(value, int) or value <= 0:
            continue
        model["context_window"] = value
        extra = model.get("extra")
        if not isinstance(extra, dict):
            extra = {}
            model["extra"] = extra
        source = override.get("source")
        if source:
            extra["context_window_source"] = source
        extra["context_window_basis"] = override.get(
            "basis", "official_metadata_fallback"
        )
        note = override.get("note")
        if note:
            extra["context_window_note"] = note
        for key in ("long_context_window", "long_context_at_standard_rates"):
            if key in override:
                extra[key] = override[key]
        applied += 1
    return applied
