"""Shared record-level capability normalizers used by catalog updaters and CLIs."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
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

VIDEO_INPUT_FORMATS = ["mp4", "mov", "webm", "mkv", "avi"]
VIDEO_INPUT_MIME_TYPES = [
    "video/mp4",
    "video/quicktime",
    "video/webm",
    "video/x-matroska",
    "video/x-msvideo",
]
VIDEO_OVERRIDES = load_overrides("video_overrides.json")

IMAGE_GENERATION_MARKERS = (
    "image",
    "imagen",
    "flux",
    "seedream",
    "diffusion",
    "openjourney",
    "z-image",
    "canvas",
    "image-generator",
    "imagine",
)
IMAGE_ANALYSIS_MARKERS = (
    "auto",
    "embedding",
    "rerank",
    "medimageparse",
    "gigatime",
    "cosmos",
)
GOOGLE_IMAGE_ASPECT_RATIOS = [
    "1:1",
    "1:4",
    "1:8",
    "2:3",
    "3:2",
    "3:4",
    "4:1",
    "4:3",
    "4:5",
    "5:4",
    "8:1",
    "9:16",
    "16:9",
    "21:9",
]
IMAGE_INPUT_OVERRIDES = load_overrides("image_overrides.json")

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
    "decision",
    "document",
    "embedding",
    "rerank",
    "spatial",
)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _source(extra: dict[str, Any]) -> str | None:
    return extra.get("official_source") or extra.get("docs_url")


def _source_url(record: dict[str, Any]) -> str | None:
    extra = record.get("extra") or {}
    for key in ("official_source", "source", "docs_url"):
        value = extra.get(key)
        if (
            isinstance(value, str)
            and value.startswith("http")
            and "pricing" not in value.lower()
        ):
            return value
    for endpoint in extra.get("endpoints") or ():
        if isinstance(endpoint, dict):
            value = endpoint.get("source")
            if isinstance(value, str) and value.startswith("http"):
                return value
    return None


def _read_json_preserving_newline(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return json.loads(raw.decode("utf-8")), newline


def _write_json(path: Path, data: dict[str, Any], newline: str) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(payload.replace("\n", newline).encode("utf-8"))


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


DERIVED_STATUSES = {"inferred", "unknown"}


def _is_derived_block(block: dict[str, Any]) -> bool:
    return bool(block) and block.get("status") in DERIVED_STATUSES


def _merge_capability_values(
    base: dict[str, Any], old: dict[str, Any], override: dict[str, Any]
) -> dict[str, Any]:
    """Merge fresh inference, preserved metadata, and explicit overrides.

    Previously inferred/unknown blocks are regenerated from the fresh source.
    Documented or legacy blocks remain authoritative over generic inference.
    Explicit overrides always win.
    """
    if _is_derived_block(old):
        merged = {**base, **override}
        if "extra" in base or "extra" in override:
            merged["extra"] = {
                **(base.get("extra") or {}),
                **(override.get("extra") or {}),
            }
        return merged

    merged = {**base, **old, **override}
    if "extra" in base or "extra" in old or "extra" in override:
        merged["extra"] = {
            **(base.get("extra") or {}),
            **(old.get("extra") or {}),
            **(override.get("extra") or {}),
        }
    return merged


def audio_generic(record: dict[str, Any]) -> dict[str, Any]:
    """Infer audio operations from explicit modalities and catalog metadata only."""
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    media_type = str(extra.get("media_model_type", "")).lower()
    tasks = {
        str(task).lower().strip()
        for task in extra.get("tasks", [])
        if str(task).strip()
    }
    has_audio_in = bool(inputs & {"audio", "speech"})
    has_audio_out = bool(outputs & {"audio", "speech"})
    if not (has_audio_in or has_audio_out):
        return {}

    result: dict[str, Any] = {
        "accepts_audio_input": has_audio_in,
        "speech_generation": has_audio_out,
        "speech_understanding": has_audio_in,
        "supports_streaming": (
            True
            if record.get("supports_streaming") is True
            or "streaming" in model_id
            or "streaming" in media_type
            or any("streaming" in task for task in tasks)
            else None
        ),
        "supports_realtime": (
            bool(record.get("supports_realtime"))
            if record.get("supports_realtime") is not None
            else None
        ),
    }
    if any(
        token in model_id or token in media_type or any(token in task for task in tasks)
        for token in (
            "transcrib",
            "translat",
            "speech-to-text",
            "speech-recognition",
            "automatic-speech-recognition",
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
    official_source = _source(extra)
    if official_source:
        result["source_url"] = official_source
        result["status"] = "inferred"
    if media_type:
        result["extra"] = {"media_model_type": media_type}
    return result


def normalize_audio_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Merge inferred audio metadata without replacing curated details."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    base = audio_generic(record)
    override = AUDIO_OVERRIDES.get((provider, model_id), {})
    old = dict(record.get("audio") or {})
    if not base and not override:
        if _is_derived_block(old):
            del record["audio"]
            return True
        return False

    merged = _merge_capability_values(base, old, override)
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
    merged.setdefault("checked_at", checked_at or _today())
    merged.setdefault("status", "documented" if override else "inferred")
    if merged == old:
        return False
    record["audio"] = merged
    return True


def video_generic(record: dict[str, Any]) -> dict[str, Any]:
    """Infer video input/output operations from explicit modalities."""
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    media_type = str(extra.get("media_model_type", "")).lower()
    has_video_in = "video" in inputs
    has_video_out = "video" in outputs
    if not (has_video_in or has_video_out):
        return {}

    result: dict[str, Any] = {
        "accepts_video_input": has_video_in,
        "generation": has_video_out,
        "understanding": has_video_in and "text" in outputs,
        "text_to_video": any(
            token in model_id or token in media_type
            for token in ("t2v", "text-to-video")
        ),
        "image_to_video": any(
            token in model_id or token in media_type
            for token in ("i2v", "image-to-video")
        ),
        "video_to_video": any(
            token in model_id or token in media_type
            for token in ("v2v", "video-to-video")
        ),
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
    official_source = _source(extra)
    if official_source:
        result["source_url"] = official_source
        result["status"] = "inferred"
    if media_type:
        result["extra"] = {"media_model_type": media_type}
    return result


def normalize_video_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Merge inferred video metadata without replacing curated details."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    base = video_generic(record)
    override = VIDEO_OVERRIDES.get((provider, model_id), {})
    old = dict(record.get("video") or {})
    if not base and not override:
        if _is_derived_block(old):
            del record["video"]
            return True
        return False

    merged = _merge_capability_values(base, old, override)
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
    merged.setdefault("checked_at", checked_at or _today())
    merged.setdefault("status", "documented" if override else "inferred")
    if merged == old:
        return False
    record["video"] = merged
    return True


def is_image_generation_record(record: dict[str, Any]) -> bool:
    """Return whether an image-output record is a recognizable generator."""
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    if "image" not in outputs:
        return False
    model_id = str(record.get("model_id", "")).lower()
    if any(marker in model_id for marker in IMAGE_ANALYSIS_MARKERS):
        return False
    return any(marker in model_id for marker in IMAGE_GENERATION_MARKERS)


def image_input_capability(record: dict[str, Any]) -> dict[str, Any]:
    """Describe image input without implying image generation."""
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    if "image" not in inputs:
        return {}
    result: dict[str, Any] = {
        "accepts_image_input": True,
        "status": "inferred",
    }
    source = _source_url(record)
    if source:
        result["source_url"] = source
    return result


def minimal_image_capability(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return a conservative capability for a recognized image generator."""
    if not is_image_generation_record(record):
        return None
    result: dict[str, Any] = {
        "generation": True,
        "accepts_text_prompt": "text" in record.get("input_modalities", []),
        "accepts_image_input": "image" in record.get("input_modalities", []),
        "status": "unknown",
    }
    source = _source_url(record)
    if source:
        result["source_url"] = source
    result.update(
        IMAGE_INPUT_OVERRIDES.get(
            (record.get("provider", ""), record.get("model_id", "")), {}
        )
    )
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    if provider == "microsoft" and model_id.lower().startswith("mai-image"):
        result.update(
            {
                "editing": True,
                "accepts_image_input": True,
                "input_formats": ["jpeg", "png"],
                "input_mime_types": ["image/jpeg", "image/png"],
                "source_url": "https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-mai-image",
                "status": "documented",
            }
        )
    if provider == "openai" and model_id in {
        "gpt-image-2.5-flare",
        "gpt-image-2.5-sunburst",
    }:
        result["endpoints"] = {
            "image_api_generations": True,
            "image_api_edits": True,
            "responses_image_tool": True,
            "chat_completions": False,
            "responses_mainline_model_required": True,
            "responses_action_values": ["auto", "generate", "edit"],
            "responses_multi_turn": True,
            "responses_image_context": True,
        }
    if provider == "meta" and model_id == "muse-image-1.0":
        result["source_url"] = "https://dev.meta.ai/docs/image-generation"
        result["endpoints"] = {
            "responses_image_tool": True,
            "image_api_generations": True,
            "image_api_edits": True,
            "chat_completions": False,
        }
    return result


def parse_image_input_constraints(text: str) -> dict[str, Any]:
    """Extract only explicit, input-specific constraints from provider docs."""
    result: dict[str, Any] = {}
    formats = re.search(
        r"(?im)^\s*(?:accepted|supported|input)\s+[^\n]*(?:format|type)s?\s*:\s*([^\n]+)$",
        text,
    )
    if formats:
        values = re.findall(
            r"\b(?:png|jpe?g|webp|gif|avif|heic)\b", formats.group(1), re.IGNORECASE
        )
        if values:
            result["input_formats"] = list(dict.fromkeys(v.lower() for v in values))
    mime_types = re.findall(
        r"\bimage/(?:png|jpe?g|webp|gif|avif|heic)\b", text, re.IGNORECASE
    )
    if mime_types:
        result["input_mime_types"] = list(dict.fromkeys(v.lower() for v in mime_types))
    byte_limit = re.search(
        r"(?i)(?:max(?:imum)?|limit)\s+(?:input\s+)?(?:image\s+)?size\s*[:：]?\s*(\d[\d,.]*)\s*(KB|MB|GB|bytes?)\b",
        text,
    )
    if byte_limit:
        amount = float(byte_limit.group(1).replace(",", ""))
        multiplier = {
            "byte": 1,
            "bytes": 1,
            "kb": 1024,
            "mb": 1024**2,
            "gb": 1024**3,
        }
        result["max_input_bytes"] = int(
            amount * multiplier[byte_limit.group(2).lower()]
        )
    dimensions = re.search(
        r"(?i)(?:max(?:imum)?\s+)?(?:input\s+)?(?:image\s+)?dimensions?\s*[:：]?\s*(\d+)\s*[x×]\s*(\d+)",
        text,
    )
    if dimensions:
        result["max_input_width"] = int(dimensions.group(1))
        result["max_input_height"] = int(dimensions.group(2))
    pixels = re.search(
        r"(?i)(?:max(?:imum)?\s+)?(?:input\s+)?(?:image\s+)?pixels?\s*[:：]?\s*(\d[\d,.]*)\s*(MP|megapixels?|pixels?)?",
        text,
    )
    if pixels:
        amount = float(pixels.group(1).replace(",", ""))
        unit = (pixels.group(2) or "pixels").lower()
        result["max_input_pixels"] = int(
            amount * 1_000_000 if unit.startswith(("mp", "mega")) else amount
        )
    return result


def known_analysis_capability(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return documented image-analysis metadata for known non-generative models."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    if provider == "microsoft" and model_id.lower() in {
        "medimageparse",
        "medimageparse3d",
    }:
        return {
            "analysis": {
                "classification": True,
                "object_detection": True,
                "segmentation": True,
            },
            "source_url": "https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/healthcare-ai/deploy-medimageparse",
            "checked_at": _today(),
            "status": "documented",
        }
    if provider == "cohere" and model_id.lower() == "embed-v-4-0":
        return {
            "analysis": {"embedding": True},
            "checked_at": _today(),
            "status": "documented",
        }
    return None


def normalize_image_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Normalize image input, generation, and known analysis metadata."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    inferred_input = image_input_capability(record)
    generation = minimal_image_capability(record) or {}
    analysis = known_analysis_capability(record) or {}
    override = IMAGE_INPUT_OVERRIDES.get((provider, model_id), {})
    base = {**inferred_input, **generation, **analysis}
    old = dict(record.get("image") or {})
    if not base and not override:
        if _is_derived_block(old):
            del record["image"]
            return True
        return False

    merged = _merge_capability_values(base, old, override)
    if base or override:
        merged.setdefault("checked_at", checked_at or _today())
    block_changed = merged != old
    if block_changed:
        record["image"] = merged
    top_changed = False
    if (
        "image" in {str(x).lower() for x in record.get("input_modalities", [])}
        and record.get("supports_vision") is not True
    ):
        record["supports_vision"] = True
        top_changed = True
    return block_changed or top_changed


def decision_generic(record: dict[str, Any]) -> dict[str, Any]:
    """Infer only the contract implied by an explicit decision output modality."""
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    if "decision" not in outputs:
        return {}
    result: dict[str, Any] = {
        "decision": True,
        "free_form_text": False,
        "status": "inferred",
    }
    source = _source_url(record)
    if source:
        result["source_url"] = source
    return result


def normalize_decision_record(
    record: dict[str, Any], *, checked_at: str | None = None
) -> bool:
    """Normalize explicit decision output without guessing provider semantics."""
    base = decision_generic(record)
    old = dict(record.get("decision") or {})
    if not base:
        if _is_derived_block(old):
            del record["decision"]
            return True
        return False
    merged = _merge_capability_values(base, old, {})
    merged.setdefault("checked_at", checked_at or _today())
    top_changed = False
    if (
        "decision" in {str(x).lower() for x in record.get("output_modalities", [])}
        and record.get("supports_chat_completion") is not False
    ):
        record["supports_chat_completion"] = False
        top_changed = True
    block_changed = merged != old
    if block_changed:
        record["decision"] = merged
    return block_changed or top_changed


def structured_generic(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    inputs = {str(x).lower() for x in record.get("input_modalities", [])}
    outputs = {str(x).lower() for x in record.get("output_modalities", [])}
    extra = record.get("extra") or {}
    model_id = str(record.get("model_id", "")).lower()
    result: dict[str, dict[str, Any]] = {}
    source = _source(extra)
    status = "inferred"

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
    structured_fields = ("document", "embedding", "rerank", "spatial")
    derived_existing = {
        key
        for key in structured_fields
        if _is_derived_block(dict(record.get(key) or {}))
    }
    keys = set(inferred) | set(overrides) | derived_existing
    if not keys:
        return False

    stamp = checked_at or _today()
    changed = False
    for key in keys:
        base = inferred.get(key, {})
        override = overrides.get(key, {})
        old = dict(record.get(key) or {})
        if not base and not override and _is_derived_block(old):
            del record[key]
            changed = True
            continue
        merged = _merge_capability_values(base, old, override)
        merged.setdefault("checked_at", stamp)
        if merged != old:
            record[key] = merged
            changed = True
    return changed


def normalize_record(record: dict[str, Any], *, checked_at: str | None = None) -> bool:
    """Apply all record-level capability normalizers."""
    changed = False
    changed = normalize_audio_record(record, checked_at=checked_at) or changed
    changed = normalize_video_record(record, checked_at=checked_at) or changed
    changed = normalize_image_record(record, checked_at=checked_at) or changed
    changed = normalize_decision_record(record, checked_at=checked_at) or changed
    changed = normalize_structured_record(record, checked_at=checked_at) or changed
    return changed


def _apply_one(
    data_dir: Path,
    predicate: Any,
    normalizer: Any,
) -> dict[str, int]:
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data, newline = _read_json_preserving_newline(path)
        file_changed = False
        for record in data.get("models", []):
            if not predicate(record):
                continue
            checked += 1
            if normalizer(record):
                changed[str(record.get("provider", "")) or path.stem] += 1
                file_changed = True
        if file_changed:
            _write_json(path, data, newline)
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }


def apply_audio(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _apply_one(
        data_dir,
        lambda record: bool(
            audio_generic(record)
            or AUDIO_OVERRIDES.get(
                (str(record.get("provider", "")), str(record.get("model_id", ""))),
                {},
            )
            or _is_derived_block(dict(record.get("audio") or {}))
        ),
        normalize_audio_record,
    )


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


def apply_video(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _apply_one(
        data_dir,
        lambda record: bool(
            video_generic(record)
            or VIDEO_OVERRIDES.get(
                (str(record.get("provider", "")), str(record.get("model_id", ""))),
                {},
            )
            or _is_derived_block(dict(record.get("video") or {}))
        ),
        normalize_video_record,
    )


def audit_video(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
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


def apply_image(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    changed = Counter()
    for path in sorted(data_dir.glob("*.json")):
        data, newline = _read_json_preserving_newline(path)
        file_changed = False
        for record in data.get("models", []):
            if normalize_image_record(record):
                changed[str(record.get("provider", path.stem))] += 1
                file_changed = True
        if file_changed:
            _write_json(path, data, newline)
    return dict(sorted(changed.items()))


def audit_image(data_dir: Path = DEFAULT_DATA) -> dict[str, Any]:
    """Report image-output records that still lack normalized image metadata."""
    missing: dict[str, list[str]] = defaultdict(list)
    ambiguous: dict[str, list[str]] = defaultdict(list)
    image_records = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            if "image" not in {
                str(x).lower() for x in record.get("output_modalities", [])
            }:
                continue
            image_records += 1
            provider = str(record.get("provider", path.stem))
            model_id = str(record.get("model_id", ""))
            if record.get("image") is not None:
                continue
            if is_image_generation_record(record):
                missing[provider].append(model_id)
            else:
                ambiguous[provider].append(model_id)
    return {
        "image_output_records": image_records,
        "missing_generation_capability": dict(sorted(missing.items())),
        "ambiguous_or_analysis_output": dict(sorted(ambiguous.items())),
    }


def apply_structured(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    return _apply_one(
        data_dir,
        lambda record: bool(
            structured_generic(record)
            or STRUCTURED_OVERRIDES.get(
                (str(record.get("provider", "")), str(record.get("model_id", ""))),
                {},
            )
            or any(
                _is_derived_block(dict(record.get(key) or {}))
                for key in ("document", "embedding", "rerank", "spatial")
            )
        ),
        normalize_structured_record,
    )


def audit_structured(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    counts = Counter()
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            for key in ("document", "embedding", "rerank", "spatial"):
                if record.get(key):
                    counts[key] += 1
    return dict(sorted(counts.items()))


def apply_all(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    """Normalize all bundled records in one read/write pass per catalog file."""
    changed = Counter()
    checked = 0
    for path in sorted(data_dir.glob("*.json")):
        data, newline = _read_json_preserving_newline(path)
        file_changed = False
        for record in data.get("models", []):
            checked += 1
            if normalize_record(record):
                changed[str(record.get("provider", "")) or path.stem] += 1
                file_changed = True
        if file_changed:
            _write_json(path, data, newline)
    return {
        "records_checked": checked,
        "records_changed": sum(changed.values()),
        **{f"provider:{k}": v for k, v in sorted(changed.items())},
    }
