"""Normalize detailed video input/output metadata in bundled catalogs.

The catalog already records video modalities. This pass adds a conservative
``video`` object and preserves provider-specific media metadata without
inventing limits that are not documented.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from _metadata_loader import load_overrides
except ImportError:  # package-style test imports
    from scripts._metadata_loader import load_overrides

DEFAULT_DATA = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"

VIDEO_INPUT_FORMATS = ["mp4", "mov", "webm", "mkv", "avi"]
VIDEO_INPUT_MIME_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
]

VIDEO_OVERRIDES = load_overrides("video_overrides.json")


def _generic(record: dict[str, Any]) -> dict[str, Any]:
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    media_type = str(extra.get("media_model_type", "")).lower()
    has_video_in = "video" in inputs
    has_video_out = "video" in outputs
    if not (has_video_in or has_video_out):
        return {}
    text_to_video = any(
        token in model_id or token in media_type for token in ("t2v", "text-to-video")
    )
    image_to_video = any(
        token in model_id or token in media_type for token in ("i2v", "image-to-video")
    )
    video_to_video = any(
        token in model_id or token in media_type for token in ("v2v", "video-to-video")
    )
    result: dict[str, Any] = {
        "accepts_video_input": has_video_in,
        "generation": has_video_out,
        "understanding": has_video_in and "text" in outputs,
        "text_to_video": text_to_video,
        "image_to_video": image_to_video,
        "video_to_video": video_to_video,
        "supports_streaming": (
            bool(record.get("supports_streaming"))
            if record.get("supports_streaming") is not None
            else None
        ),
        "supports_realtime": (
            bool(record.get("supports_realtime"))
            if record.get("supports_realtime") is not None
            else None
        ),
    }
    if any(
        token in model_id or token in media_type
        for token in ("edit", "extend", "upscale", "interpolation")
    ):
        result["editing"] = True
    if "lipsync" in model_id or "lip-sync" in media_type or "avatar" in media_type:
        result["lipsync"] = True
    if "avatar" in model_id or "avatar" in media_type:
        result["avatar"] = True
    official_source = extra.get("official_source") or extra.get("docs_url")
    if official_source:
        result["source_url"] = official_source
        result["status"] = "documented"
    if media_type:
        result["extra"] = {"media_model_type": media_type}
    return result


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        for record in data.get("models", []):
            provider = str(record.get("provider", ""))
            model_id = str(record.get("model_id", ""))
            base = _generic(record)
            override = VIDEO_OVERRIDES.get((provider, model_id), {})
            if not base and not override:
                continue
            old = dict(record.get("video") or {})
            merged = {**old, **base, **override}
            merged["extra"] = {
                **(old.get("extra") or {}),
                **(base.get("extra") or {}),
                **(override.get("extra") or {}),
            }
            endpoint = dict(merged.get("endpoints") or {})
            for key in (
                "generation",
                "understanding",
                "editing",
                "interpolation",
                "extension",
                "upscaling",
                "lipsync",
            ):
                if merged.get(key):
                    endpoint.setdefault(key, True)
            if merged.get("supports_realtime"):
                endpoint.setdefault("realtime", True)
            if merged.get("supports_streaming"):
                endpoint.setdefault("streaming", True)
            if endpoint:
                merged["endpoints"] = endpoint
            if merged.get("generation") and not merged.get("output_formats"):
                merged["output_formats"] = ["mp4"]
                merged["output_mime_types"] = ["video/mp4"]
            if merged.get("accepts_video_input") and not merged.get("input_formats"):
                merged["input_formats"] = VIDEO_INPUT_FORMATS
                merged["input_mime_types"] = VIDEO_INPUT_MIME_TYPES
            merged["checked_at"] = datetime.now(timezone.utc).date().isoformat()
            merged.setdefault("status", "documented" if override else "inferred")
            if merged != old:
                record["video"] = merged
                changed[provider or path.stem] += 1
                file_changed = True
            checked += 1
        if file_changed:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    counts = Counter()
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            if "video" in {
                str(x).lower()
                for x in record.get("input_modalities", [])
                + record.get("output_modalities", [])
            }:
                counts[record.get("provider", path.stem)] += 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(
        json.dumps({"video_records_by_provider": audit()}, ensure_ascii=False, indent=2)
    )
