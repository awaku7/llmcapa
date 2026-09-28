"""Normalize detailed audio input/output metadata in bundled catalogs."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import _capability_normalizers as _normalizers
except ImportError:  # package-style test imports
    from scripts import _capability_normalizers as _normalizers

AUDIO_INPUT_FORMATS = _normalizers.AUDIO_INPUT_FORMATS
AUDIO_INPUT_MIME_TYPES = _normalizers.AUDIO_INPUT_MIME_TYPES
AUDIO_OVERRIDES = _normalizers.AUDIO_OVERRIDES
DEFAULT_DATA = _normalizers.DEFAULT_DATA
normalize_audio_record = _normalizers.normalize_audio_record
_generic = _normalizers.audio_generic


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.apply_audio(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.audit_audio(data_dir)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(
        json.dumps({"audio_records_by_provider": audit()}, ensure_ascii=False, indent=2)
    )
