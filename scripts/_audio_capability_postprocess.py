"""Normalize detailed audio input/output metadata in bundled catalogs.

The catalog updaters already record audio modalities. This pass adds a
provider-neutral ``audio`` object without guessing values that are not
explicitly documented. Exact constraints are limited to values confirmed by
provider documentation; the generic pass only derives operations from the
catalog modalities and model metadata.
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

AUDIO_INPUT_FORMATS = [
    "flac",
    "mp3",
    "mp4",
    "mpeg",
    "mpga",
    "m4a",
    "ogg",
    "wav",
    "webm",
]
AUDIO_INPUT_MIME_TYPES = [
    "audio/flac",
    "audio/mpeg",
    "audio/mp4",
    "audio/ogg",
    "audio/wav",
    "audio/webm",
]

# Explicit values are restricted to provider documentation. The generic
# capability below remains conservative for models not covered here.
AUDIO_OVERRIDES = load_overrides("audio_overrides.json")


def _generic(record: dict[str, Any]) -> dict[str, Any]:
    """Infer operations from explicit modalities and catalog metadata only."""
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    media_type = str(extra.get("media_model_type", "")).lower()
    has_audio_in = bool(inputs & {"audio", "speech"})
    has_audio_out = bool(outputs & {"audio", "speech"})
    if not (has_audio_in or has_audio_out):
        return {}
    result: dict[str, Any] = {
        "accepts_audio_input": has_audio_in,
        "speech_generation": has_audio_out,
        "speech_understanding": has_audio_in,
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
        for token in (
            "transcrib",
            "translat",
            "speech-to-text",
            "stt",
            "asr",
            "whisper",
        )
    ):
        result["transcription"] = True
    if "diariz" in model_id or "diariz" in media_type:
        result["diarization"] = True
    if "music" in model_id or "music" in media_type:
        result["music_generation"] = True
    if "tts" in model_id or "text-to-speech" in media_type or "voice" in media_type:
        result["speech_generation"] = True
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
            override = AUDIO_OVERRIDES.get((provider, model_id), {})
            if not base and not override:
                continue
            old = dict(record.get("audio") or {})
            merged = {**old, **base, **override}
            merged["extra"] = {
                **(old.get("extra") or {}),
                **(base.get("extra") or {}),
                **(override.get("extra") or {}),
            }
            endpoint = dict(merged.get("endpoints") or {})
            if merged.get("transcription"):
                endpoint.setdefault("transcription", True)
            if merged.get("translation"):
                endpoint.setdefault("translation", True)
            if merged.get("speech_generation"):
                endpoint.setdefault("speech_generation", True)
            if merged.get("speech_understanding"):
                endpoint.setdefault("speech_understanding", True)
            if merged.get("supports_realtime"):
                endpoint.setdefault("realtime", True)
            if merged.get("supports_streaming"):
                endpoint.setdefault("streaming", True)
            if endpoint:
                merged["endpoints"] = endpoint
            merged["checked_at"] = datetime.now(timezone.utc).date().isoformat()
            merged.setdefault("status", "documented" if override else "inferred")
            if merged != old:
                record["audio"] = merged
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
            if "audio" in {
                str(x).lower()
                for x in record.get("input_modalities", [])
                + record.get("output_modalities", [])
            }:
                counts[record.get("provider", path.stem)] += 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    print(json.dumps(apply(), ensure_ascii=False, indent=2))
    print(
        json.dumps({"audio_records_by_provider": audit()}, ensure_ascii=False, indent=2)
    )
