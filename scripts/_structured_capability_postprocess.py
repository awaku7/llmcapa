"""Normalize document, embedding, rerank, and spatial metadata."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import _capability_normalizers as _normalizers
except ImportError:  # package-style test imports
    from scripts import _capability_normalizers as _normalizers

DEFAULT_DATA = _normalizers.DEFAULT_DATA
DOCUMENT_FORMATS = _normalizers.DOCUMENT_FORMATS
DOCUMENT_MIMES = _normalizers.DOCUMENT_MIMES
OVERRIDES = _normalizers.STRUCTURED_OVERRIDES
normalize_structured_record = _normalizers.normalize_structured_record
_generic = _normalizers.structured_generic


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.apply_structured(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.audit_structured(data_dir)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(json.dumps({"records_by_capability": audit()}, ensure_ascii=False, indent=2))
