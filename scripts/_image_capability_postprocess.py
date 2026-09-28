"""Compatibility CLI for shared image capability normalization."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    import _capability_normalizers as _normalizers
except ImportError:  # package-style test imports
    from scripts import _capability_normalizers as _normalizers

DEFAULT_DATA = _normalizers.DEFAULT_DATA
GOOGLE_IMAGE_ASPECT_RATIOS = _normalizers.GOOGLE_IMAGE_ASPECT_RATIOS
IMAGE_INPUT_OVERRIDES = _normalizers.IMAGE_INPUT_OVERRIDES
_is_generation_record = _normalizers.is_image_generation_record
minimal_image_capability = _normalizers.minimal_image_capability
parse_image_input_constraints = _normalizers.parse_image_input_constraints
known_analysis_capability = _normalizers.known_analysis_capability
normalize_image_record = _normalizers.normalize_image_record


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _normalizers.apply_image(data_dir)


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, object]:
    return _normalizers.audit_image(data_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--write", action="store_true", help="normalize image records")
    args = parser.parse_args()
    if args.write:
        print(
            json.dumps({"changed": apply(args.data_dir)}, ensure_ascii=False, indent=2)
        )
    print(json.dumps(audit(args.data_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
