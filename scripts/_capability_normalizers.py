"""Shared record-level capability normalizers used by catalog updaters and CLIs."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from _metadata_loader import load_overrides
except ImportError:  # package-style imports in tests/tools
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
AUDIO_OVERRIDES = load_overrides("audio_overrides.json")

DOCUMENT_FORMATS = [
    "pdf",
    "txt",
    "md",
    "csv",
    "json",
    "xml",
    "html",
    "docx",
    "xlsx",
    "pptx",
]
DOCUMENT_MIMES = [
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "text/html",
]
STRUCTURED_OVERRIDES = load_overrides("structured_overrides.json")

CAPABILITY_FIELDS = (
    "audio",
    "video",
    "image",
    "document",
    "embedding",
    "rerank",
    "spatial",
)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def preserve_capability_blocks(
    record: dict[str, Any], previous: dict[str, Any] | None
) -> bool:
    """Copy existing curated capability blocks before derived normalization."""
    if not previous:
        return False
    changed = False
    for field in CAPABILITY_FIELDS:
        if field not in record and field in previous:
            record[field] = previous[field]
            changed = True
    return changed


def audio_generic(record: dict[str, Any]) -> dict[str, Any]:
    """Infer audio operations from explicit modalities and catalog metadata only."""
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


def normalize_audio_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Merge inferred/overridden audio metadata into one in-memory model record."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    base = audio_generic(record)
    override = AUDIO_OVERRIDES.get((provider, model_id), {})
    if not base and not override:
        return False

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
    merged["checked_at"] = checked_at or _today()
    merged.setdefault("status", "documented" if override else "inferred")
    if merged == old:
        return False
    record["audio"] = merged
    return True


def _source(extra: dict[str, Any]) -> str | None:
    return extra.get("official_source") or extra.get("docs_url")


def structured_generic(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    result: dict[str, dict[str, Any]] = {}
    source = _source(extra)
    status = "documented" if source else "inferred"

    file_like = inputs & {"file", "pdf", "csv", "json", "code", "data"}
    if file_like or outputs & {"file", "pdf", "csv", "json"}:
        doc: dict[str, Any] = {
            "accepts_file": bool(file_like),
            "input_formats": sorted(file_like) if file_like else DOCUMENT_FORMATS,
            "input_mime_types": DOCUMENT_MIMES,
            "status": status,
        }
        if source:
            doc["source_url"] = source
        if any(x in model_id for x in ("ocr", "document", "layout", "parse", "vision")):
            doc["ocr"] = True
        result["document"] = doc

    if outputs & {"embedding", "embeddings"} or any(
        x in model_id for x in ("embedding", "embed")
    ):
        emb: dict[str, Any] = {
            "embedding": True,
            "output_formats": ["float"],
            "status": status,
        }
        if source:
            emb["source_url"] = source
        result["embedding"] = emb

    if "rerank" in outputs or "rerank" in model_id:
        rr: dict[str, Any] = {
            "rerank": True,
            "returns_scores": True,
            "status": status,
        }
        if source:
            rr["source_url"] = source
        result["rerank"] = rr

    spatial_kinds = inputs | outputs
    if spatial_kinds & {"3d-image", "geospatial"}:
        sp: dict[str, Any] = {
            "spatial": True,
            "kind_values": sorted(spatial_kinds & {"3d-image", "geospatial"}),
            "supports_3d": "3d-image" in spatial_kinds,
            "supports_geospatial": "geospatial" in spatial_kinds,
            "status": status,
        }
        if source:
            sp["source_url"] = source
        result["spatial"] = sp
    return result


def normalize_structured_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Merge document/embedding/rerank/spatial metadata into one record."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    inferred = structured_generic(record)
    overrides = STRUCTURED_OVERRIDES.get((provider, model_id), {})
    capabilities = {**inferred}
    for key, value in overrides.items():
        capabilities[key] = {**capabilities.get(key, {}), **value}
    if not capabilities:
        return False

    stamp = checked_at or _today()
    changed = False
    for key, value in capabilities.items():
        old = dict(record.get(key) or {})
        merged = {**old, **value}
        merged["checked_at"] = stamp
        if merged != old:
            record[key] = merged
            changed = True
    return changed


def normalize_record(record: dict[str, Any], *, checked_at: str | None = None) -> bool:
    """Apply all record-level normalizers available in this module."""
    audio_changed = normalize_audio_record(record, checked_at=checked_at)
    structured_changed = normalize_structured_record(record, checked_at=checked_at)
    return audio_changed or structured_changed


def apply_audio(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        for record in data.get("models", []):
            if not audio_generic(record) and not AUDIO_OVERRIDES.get(
                (str(record.get("provider", "")), str(record.get("model_id", ""))), {}
            ):
                continue
            checked += 1
            if normalize_audio_record(record):
                changed[str(record.get("provider", "")) or path.stem] += 1
                file_changed = True
        if file_changed:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }


def audit_audio(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
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


def apply_structured(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        file_changed = False
        for record in data.get("models", []):
            provider = str(record.get("provider", ""))
            model_id = str(record.get("model_id", ""))
            if not structured_generic(record) and not STRUCTURED_OVERRIDES.get(
                (provider, model_id), {}
            ):
                continue
            checked += 1
            if normalize_structured_record(record):
                changed[provider or path.stem] += 1
                file_changed = True
        if file_changed:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }


def audit_structured(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    counts = Counter()
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            for key in ("document", "embedding", "rerank", "spatial"):
                if record.get(key):
                    counts[key] += 1
    return dict(sorted(counts.items()))
