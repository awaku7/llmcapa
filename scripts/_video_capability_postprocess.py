"""Compatibility CLI for shared video capability normalization."""

from __future__ import annotations

import json
from pathlib import Path

try:
    import _capability_normalizers as _normalizers
except ImportError:  # package-style test imports
    from scripts import _capability_normalizers as _normalizers

DEFAULT_DATA = _normalizers.DEFAULT_DATA
VIDEO_INPUT_FORMATS = _normalizers.VIDEO_INPUT_FORMATS
VIDEO_INPUT_MIME_TYPES = _normalizers.VIDEO_INPUT_MIME_TYPES
VIDEO_OVERRIDES = _normalizers.VIDEO_OVERRIDES
_generic = _normalizers.video_generic
normalize_video_record = _normalizers.normalize_video_record


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.apply_video(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.audit_video(data_dir)


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(
        json.dumps({"video_records_by_provider": audit()}, ensure_ascii=False, indent=2)
    )
