"""Rewrite bundled catalog JSONs in the compact on-disk format.

Applies ``llmcapa._catalog_format.dump_catalog`` to every
``src/llmcapa/data/*.json`` that holds a plain ``{"models": [...]}``
payload. HF overlay catalogs already store deltas and are skipped.

Every payload is verified before its file is rewritten: parsing the
compact text must reproduce the original payload exactly, so the
migration cannot change what the library loads.

Run from the repository root:

    python scripts/compact_catalog_jsons.py

Follow with ``python scripts/build_catalog_db.py`` to rebuild the
SQLite catalog.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from llmcapa._catalog_format import dump_catalog
from llmcapa.hf_overlay import is_hf_overlay

DATA = ROOT / "src" / "llmcapa" / "data"


def main() -> None:
    total_before = total_after = 0
    for path in sorted(DATA.glob("*.json")):
        payload = json.loads(path.read_bytes().decode("utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"models"}:
            reason = "hf overlay" if is_hf_overlay(payload) else "other shape"
            print(f"skip {path.name} ({reason})")
            continue
        text = dump_catalog(payload)
        if json.loads(text) != payload:
            raise ValueError(f"round-trip mismatch in {path.name}")
        before = path.stat().st_size
        path.write_bytes(text.encode("utf-8"))
        after = path.stat().st_size
        total_before += before
        total_after += after
        print(f"{path.name}: {before} -> {after} bytes")
    print(f"total: {total_before} -> {total_after} bytes")


if __name__ == "__main__":
    main()
