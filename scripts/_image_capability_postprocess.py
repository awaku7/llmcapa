"""Normalize and audit image-generation capability records.

This is intentionally conservative: image input alone is not treated as image
creation.  A record must advertise image output and have a recognizable image
generation family before a minimal ``ImageCapability`` is added.

The provider updaters remain the source of truth for detailed constraints.  If
they do not expose a documented value, this script leaves it unknown instead
of guessing.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "src" / "llmcapa" / "data"

# Model-family markers for records whose image output is an image-generation
# product rather than an image-analysis/reranking output.
_GENERATION_MARKERS = (
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
_ANALYSIS_MARKERS = (
    "auto",
    "embedding",
    "rerank",
    "medimageparse",
    "gigaTime",
    "cosmos",
)


# Values confirmed from provider documentation during the catalog audit.
# These are limited to input constraints and explicit generation controls;
# unknown values remain unset.
GOOGLE_IMAGE_ASPECT_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]
IMAGE_INPUT_OVERRIDES: dict[tuple[str, str], dict[str, Any]] = {
    ("amazon", "nova-canvas-v1"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_width": 4096,
        "max_input_height": 4096,
        "max_input_pixels": 4_194_304,
        "source_url": "https://docs.aws.amazon.com/nova/latest/userguide/image-gen-access.html",
        "status": "documented",
    },
    ("bytedance-seed", "seedream-4.5"): {
        "input_formats": ["jpeg", "png", "webp", "bmp", "tiff", "gif", "heic"],
        "input_mime_types": ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff", "image/gif", "image/heic"],
        "max_input_images": 14,
        "source_url": "https://docs.byteplus.com/en/docs/ModelArk/1541523",
        "status": "documented",
    },
    ("bytedance-seed", "seedream-5-0-pro"): {
        "input_formats": ["jpeg", "png", "webp", "bmp", "tiff", "gif", "heic"],
        "input_mime_types": ["image/jpeg", "image/png", "image/webp", "image/bmp", "image/tiff", "image/gif", "image/heic"],
        "max_input_images": 14,
        "source_url": "https://docs.byteplus.com/en/docs/ModelArk/1541523",
        "status": "documented",
    },
    ("google", "gemini-2.5-flash-image"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["1K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("google", "gemini-3-pro-image"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["1K", "2K", "4K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("google", "gemini-3-pro-image-preview"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["1K", "2K", "4K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("google", "gemini-3.1-flash-image"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["512", "1K", "2K", "4K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("google", "gemini-3.1-flash-image-preview"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["512", "1K", "2K", "4K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("google", "gemini-3.1-flash-lite-image"): {
        "input_formats": ["png", "jpeg"],
        "input_mime_types": ["image/png", "image/jpeg"],
        "max_input_payload_bytes": 20 * 1024 * 1024,
        "supported_sizes": ["1K"],
        "supported_aspect_ratios": GOOGLE_IMAGE_ASPECT_RATIOS,
        "supports_transparent_background": False,
        "source_url": "https://ai.google.dev/gemini-api/docs/generate-content/image-generation",
        "status": "documented",
    },
    ("xai", "grok-imagine-image"): {
        "input_formats": ["jpg", "jpeg", "png"],
        "input_mime_types": ["image/jpeg", "image/png"],
        "max_input_bytes": 20 * 1024 * 1024,
        "source_url": "https://docs.x.ai/developers/model-capabilities/images/understanding",
        "status": "documented",
    },
    ("xai", "grok-imagine-image-quality"): {
        "input_formats": ["jpg", "jpeg", "png"],
        "input_mime_types": ["image/jpeg", "image/png"],
        "max_input_bytes": 20 * 1024 * 1024,
        "source_url": "https://docs.x.ai/developers/model-capabilities/images/understanding",
        "status": "documented",
    },
    ("xai", "grok-imagine-image-2.0"): {
        "input_formats": ["jpg", "jpeg", "png"],
        "input_mime_types": ["image/jpeg", "image/png"],
        "max_input_bytes": 20 * 1024 * 1024,
        "source_url": "https://docs.x.ai/developers/model-capabilities/images/generation.md",
        "status": "documented",
    },
    ("meta", "muse-image-1.0"): {
        "editing": True,
        "accepts_file_id": True,
        "accepts_image_url": True,
        "input_formats": ["jpeg", "png"],
        "input_mime_types": ["image/jpeg", "image/png"],
        "max_input_bytes": 50_000_000,
        "max_input_file_bytes": 1_073_741_824,
        "source_url": "https://dev.meta.ai/docs/image-understanding/",
        "status": "documented",
    },
    ("minimax", "image-01"): {
        "accepts_image_input": True,
        "input_formats": ["jpg", "jpeg", "png", "webp", "heic", "heif"],
        "input_mime_types": ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"],
        "max_input_bytes": 30 * 1024 * 1024,
        "source_url": "https://platform.minimax.io/docs/api-reference/file-management-upload",
        "status": "documented",
    },
    ("qwen", "qwen-image-2.0-pro"): {
        "accepts_image_input": True,
        "input_formats": ["jpg", "jpeg", "png", "bmp", "tiff", "webp", "gif"],
        "input_mime_types": ["image/jpeg", "image/png", "image/bmp", "image/tiff", "image/webp", "image/gif"],
        "max_input_bytes": 10 * 1024 * 1024,
        "source_url": "https://help.aliyun.com/en/model-studio/qwen-image-edit-api",
        "status": "documented",
    },
}

def _is_generation_record(record: dict[str, Any]) -> bool:
    modalities = {str(x).lower() for x in record.get("output_modalities", [])}
    if "image" not in modalities:
        return False
    model_id = str(record.get("model_id", "")).lower()
    if any(marker.lower() in model_id for marker in _ANALYSIS_MARKERS):
        return False
    return any(marker in model_id for marker in _GENERATION_MARKERS)


def _source_url(record: dict[str, Any]) -> str | None:
    extra = record.get("extra") or {}
    for key in ("official_source", "source"):
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


def minimal_image_capability(record: dict[str, Any]) -> dict[str, Any] | None:
    """Return a conservative capability for a recognized image generator."""
    if not _is_generation_record(record):
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
        result["status"] = "documented"
    result.update(IMAGE_INPUT_OVERRIDES.get((record.get("provider", ""), record.get("model_id", "")), {}))
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
    if provider == "openai" and model_id in {"gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}:
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
        multiplier = {"byte": 1, "bytes": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3}
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
    """Return documented image-analysis metadata for non-generative records."""
    provider = str(record.get("provider", ""))
    model_id = str(record.get("model_id", ""))
    if provider == "microsoft" and model_id.lower() in {"medimageparse", "medimageparse3d"}:
        return {
            "analysis": {
                "classification": True,
                "object_detection": True,
                "segmentation": True,
            },
            "source_url": "https://learn.microsoft.com/en-us/azure/foundry-classic/how-to/healthcare-ai/deploy-medimageparse",
            "checked_at": datetime.now(timezone.utc).date().isoformat(),
            "status": "documented",
        }
    if provider == "cohere" and model_id.lower() == "embed-v-4-0":
        return {
            "analysis": {"embedding": True},
            "checked_at": datetime.now(timezone.utc).date().isoformat(),
            "status": "documented",
        }
    return None


def audit(data_dir: Path = DEFAULT_DATA) -> dict[str, Any]:
    """Report image-output records that still lack ImageCapability."""
    missing: dict[str, list[str]] = defaultdict(list)
    ambiguous: dict[str, list[str]] = defaultdict(list)
    image_records = 0
    for path in sorted(data_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for record in data.get("models", []):
            if "image" not in {str(x).lower() for x in record.get("output_modalities", [])}:
                continue
            image_records += 1
            provider = str(record.get("provider", path.stem))
            model_id = str(record.get("model_id", ""))
            if record.get("image") is not None:
                continue
            if _is_generation_record(record):
                missing[provider].append(model_id)
            else:
                ambiguous[provider].append(model_id)
    return {
        "image_output_records": image_records,
        "missing_generation_capability": dict(sorted(missing.items())),
        "ambiguous_or_analysis_output": dict(sorted(ambiguous.items())),
    }


def apply(data_dir: Path = DEFAULT_DATA) -> dict[str, int]:
    """Add only conservative missing ImageCapability records to catalogs."""
    changed = Counter()
    for path in sorted(data_dir.glob("*.json")):
        raw = path.read_bytes()
        crlf = b"\r\n" in raw
        text = raw.decode("utf-8").replace("\r\n", "\n")
        data = json.loads(text)
        file_changed = False
        for record in data.get("models", []):
            provider = str(record.get("provider", ""))
            model_id = str(record.get("model_id", ""))
            override = IMAGE_INPUT_OVERRIDES.get((provider, model_id), {})
            dynamic_override = (
                provider == "microsoft" and model_id.lower().startswith("mai-image")
            ) or (
                provider == "openai"
                and model_id in {"gpt-image-2.5-flare", "gpt-image-2.5-sunburst"}
            ) or (provider == "meta" and model_id == "muse-image-1.0")
            if record.get("image") is not None and not override and not dynamic_override:
                continue
            capability = minimal_image_capability(record)
            analysis_capability = known_analysis_capability(record)
            if capability is None and analysis_capability is None and not override:
                continue
            merged = dict(record.get("image") or {})
            merged.update(capability or {})
            merged.update(analysis_capability or {})
            merged.update(override)
            if provider == "meta" and model_id == "muse-image-1.0":
                merged["source_url"] = "https://dev.meta.ai/docs/image-generation"
                merged["endpoints"] = {
                    "responses_image_tool": True,
                    "image_api_generations": True,
                    "image_api_edits": True,
                    "chat_completions": False,
                }
            if capability is not None or analysis_capability is not None or override:
                merged.setdefault("checked_at", datetime.now(timezone.utc).date().isoformat())
            if merged == record.get("image"):
                continue
            record["image"] = merged
            changed[str(record.get("provider", path.stem))] += 1
            file_changed = True
        if file_changed:
            payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
            path.write_bytes(
                (payload.replace("\n", "\r\n") if crlf else payload).encode("utf-8")
            )
    return dict(sorted(changed.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--write", action="store_true", help="add conservative records")
    args = parser.parse_args()
    if args.write:
        print(json.dumps({"changed": apply(args.data_dir)}, ensure_ascii=False, indent=2))
    print(json.dumps(audit(args.data_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
