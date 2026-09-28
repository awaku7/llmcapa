"""Normalize detailed audio input/output metadata in bundled catalogs."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from _capability_normalizers import (
        AUDIO_INPUT_FORMATS,
        AUDIO_INPUT_MIME_TYPES,
        AUDIO_OVERRIDES,
        DEFAULT_DATA,
        apply_audio,
        audit_audio,
        audio_generic,
        normalize_audio_record,
    )
except ImportError:  # package-style test imports
    from scripts._capability_normalizers import (
        AUDIO_INPUT_FORMATS,
        AUDIO_INPUT_MIME_TYPES,
        AUDIO_OVERRIDES,
        DEFAULT_DATA,
        apply_audio,
        audit_audio,
        audio_generic,
        normalize_audio_record,
    )

_generic = audio_generic


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return apply_audio(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return audit_audio(data_dir)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(
        json.dumps({"audio_records_by_provider": audit()}, ensure_ascii=False, indent=2)
    )
