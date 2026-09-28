"""Normalize document, embedding, rerank, and spatial metadata."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from _capability_normalizers import (
        DEFAULT_DATA,
        DOCUMENT_FORMATS,
        DOCUMENT_MIMES,
        STRUCTURED_OVERRIDES,
        apply_structured,
        audit_structured,
        normalize_structured_record,
        structured_generic,
    )
except ImportError:  # package-style test imports
    from scripts._capability_normalizers import (
        DEFAULT_DATA,
        DOCUMENT_FORMATS,
        DOCUMENT_MIMES,
        STRUCTURED_OVERRIDES,
        apply_structured,
        audit_structured,
        normalize_structured_record,
        structured_generic,
    )

OVERRIDES = STRUCTURED_OVERRIDES
_generic = structured_generic


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return apply_structured(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return audit_structured(data_dir)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(json.dumps({"records_by_capability": audit()}, ensure_ascii=False, indent=2))
