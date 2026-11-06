"""Read/write compact Hugging Face-backed catalogs for postprocessors."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmcapa.hf_overlay import expand_hf_overlay, is_hf_overlay, pack_hf_overlay


def _hf_source(path: Path) -> dict[str, Any]:
    return json.loads((path.parent / "huggingface.json").read_text(encoding="utf-8"))


def load_catalog(path: Path, text: str | None = None) -> dict[str, Any]:
    """Return a regular model list from either supported on-disk format."""
    catalog = json.loads(text if text is not None else path.read_text(encoding="utf-8"))
    if is_hf_overlay(catalog):
        return expand_hf_overlay(_hf_source(path), catalog)
    return catalog


def serialize_catalog(path: Path, catalog: dict[str, Any]) -> str:
    """Preserve an overlay representation after postprocessing the model data."""
    original = json.loads(path.read_text(encoding="utf-8"))
    if is_hf_overlay(original):
        catalog = pack_hf_overlay(
            _hf_source(path), catalog, provider=original["provider"]
        )
    return json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"
