"""Compact on-disk text format for catalog JSON payloads.

Bundled catalogs are machine-maintained data files. Writing them with
``indent=2`` costs roughly 30% of their size in whitespace alone. The
compact format keeps the same JSON schema and every record field:

- one model record per line, so diffs stay per-model;
- no spaces after separators inside a record;
- any other payload shape falls back to a plain compact dump.

Reading is unaffected: loaders use :func:`json.loads`, which accepts
both the compact and the legacy pretty-printed form.
"""

from __future__ import annotations

import json
from typing import Any


def dump_catalog(payload: dict[str, Any]) -> str:
    """Serialize a catalog payload in the compact on-disk format."""
    if set(payload) == {"models"} and isinstance(payload["models"], list):
        lines = [
            json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            for record in payload["models"]
        ]
        return '{\n"models": [\n' + ",\n".join(lines) + "\n]\n}\n"
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
