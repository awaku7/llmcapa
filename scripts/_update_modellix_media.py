"""Refresh Modellix media model IDs and task metadata from its official docs.

The Modellix documentation index is the public inventory and is maintained by
Modellix. This parser adds only task types explicitly described in model docs;
pricing, numeric limits, and detailed media constraints remain unchanged or
unknown unless separately sourced.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "modellix_media.json"
INDEX_URL = "https://docs.modellix.ai/llms.txt"
MEDIA_API = "https://api.modellix.ai"

MODEL_LINK_RE = re.compile(
    r"^\s*-\s+\[([^\]]+)\]\((https://docs\.modellix\.ai/([^/]+)/([^/]+)\.md)\)\s*:?\s*(.*)$",
    re.IGNORECASE,
)


def fetch_index() -> str:
    request = Request(
        INDEX_URL,
        headers={"Accept": "text/plain,text/markdown,*/*", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=45) as response:
        text = response.read(4_000_000).decode("utf-8", "replace")
    if not text.strip() or "modellix.ai" not in text:
        raise RuntimeError("Modellix official documentation index was empty or malformed")
    return text


def classify_task(model_id: str, title: str, description: str) -> dict[str, object] | None:
    """Classify only explicit media task labels and documented core functions."""
    identity = f"{model_id} {title}".casefold().replace("_", "-")
    core = description.casefold()
    if "[core function]" in core:
        core = core.split("[core function]", 1)[1].split("[strengths]", 1)[0]
    haystack = f"{identity} {core}"
    has_core_description = "[core function]" in description.casefold()

    if any(marker in identity for marker in ("first-last-frame", "first-last", "fl2v")):
        return {"input_modalities": ["text", "image"], "output_modalities": ["video"], "media_model_type": "image-to-video"}
    if "motion-control" in identity:
        return {"input_modalities": ["text", "image", "video"], "output_modalities": ["video"], "media_model_type": "video-to-video"}
    if any(marker in identity for marker in ("video-effects", "digital-human", "multi-frame", "template-story", "one-click", "q3-drama")):
        inputs = ["text", "image"]
        if "digital-human" in identity or "avatar" in identity:
            inputs.append("audio")
        if "trending-replicate" in identity:
            inputs.append("video")
        return {"input_modalities": inputs, "output_modalities": ["video"], "media_model_type": "image-to-video"}
    if "kling-avatar" in identity:
        return {"input_modalities": ["text", "image", "audio"], "output_modalities": ["video"], "media_model_type": "image-to-video"}
    if any(marker in identity for marker in ("video-upscale", "upscale-video", "video-restyle", "video-edit", "video-o1", "video-extend", "video-effects")):
        return {"input_modalities": ["text", "video"], "output_modalities": ["video"], "media_model_type": "video-to-video"}
    if any(marker in identity for marker in ("image-o1", "image-expansion", "kling-image")):
        return {"input_modalities": ["text", "image"], "output_modalities": ["image"], "media_model_type": "image-editing"}
    if "nano-banana" in identity:
        return {"input_modalities": ["text"], "output_modalities": ["image"], "media_model_type": "text-to-image"}
    if "imagine-image" in identity:
        return {"input_modalities": ["text"], "output_modalities": ["image"], "media_model_type": "text-to-image"}
    if any(marker in identity for marker in ("voice-clone", "cosyvoice-clone")):
        return {"input_modalities": ["text", "audio"], "output_modalities": ["audio"], "media_model_type": "text-to-speech"}
    if "cosyvoice-design" in identity:
        return {"input_modalities": ["text"], "output_modalities": ["audio"], "media_model_type": "text-to-speech"}

    if any(marker in haystack for marker in ("video-to-video", "video to video", "video editing", "extend an existing video", "video extend", "v2v")):
        return {"input_modalities": ["text", "video"], "output_modalities": ["video"], "media_model_type": "video-to-video"}
    if any(marker in haystack for marker in ("image-to-video", "image to video", "reference-to-video", "i2v", "r2v")):
        return {"input_modalities": ["text", "image"], "output_modalities": ["video"], "media_model_type": "image-to-video"}
    if any(marker in haystack for marker in ("text-to-video", "text to video", "t2v")):
        return {"input_modalities": ["text"], "output_modalities": ["video"], "media_model_type": "text-to-video"}
    if any(marker in haystack for marker in ("speech-to-text", "speech to text", "transcription", "transcribe", "automatic speech recognition", "asr")):
        return {"input_modalities": ["audio"], "output_modalities": ["text"], "media_model_type": "speech-to-text"}
    if any(marker in haystack for marker in ("text-to-speech", "text to speech", "speech generation", "voice generation", "tts")):
        return {"input_modalities": ["text"], "output_modalities": ["audio"], "media_model_type": "text-to-speech"}
    if any(marker in identity for marker in ("image-edit", "image-editing", "-edit")) or any(marker in core for marker in ("image editing", "image edit", "edit an image", "edit existing image", "i2i")):
        return {"input_modalities": ["text", "image"], "output_modalities": ["image"], "media_model_type": "image-editing"}
    if any(marker in haystack for marker in ("text-to-image", "text to image", "image generation", "generate images", "t2i")):
        return {"input_modalities": ["text"], "output_modalities": ["image"], "media_model_type": "text-to-image"}
    if has_core_description:
        # A model page exists but does not state a recognized task category.
        return None
    return None


def parse_catalog_index(text: str) -> tuple[list[dict], list[str]]:
    rows: dict[str, dict] = {}
    skipped: list[str] = []
    for line in text.splitlines():
        match = MODEL_LINK_RE.match(line)
        if not match:
            continue
        title, url, provider, slug, description = match.groups()
        if "[Core Function]" not in description:
            continue
        model_id = f"{provider}/{slug}"
        task = classify_task(model_id, title, description)
        if task is None:
            skipped.append(model_id)
            continue
        rows[model_id.casefold()] = {
            "provider": "modellix",
            "model_id": model_id,
            "display_name": title.strip(),
            "context_window": 0,
            "max_output_tokens": 0,
            **task,
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_streaming": False,
            "supports_vision": "image" in task["input_modalities"],
            "supports_reasoning": None,
            "supports_chat_completion": False,
            "supports_responses_api": False,
            "pricing": None,
            "deprecated": False,
            "aliases": [],
            "license_type": "api",
            "extra": {
                "official_source": url,
                "gateway_base_url": MEDIA_API,
                "media_model_type": task["media_model_type"],
                "official_description": description.strip(),
            },
        }
    if not rows:
        raise ValueError("No classifiable media model pages were found in Modellix llms.txt")
    return list(rows.values()), skipped


def merge_catalog(fresh: list[dict], previous: list[dict], checked_at: str) -> list[dict]:
    old_by_id = {
        str(model.get("model_id", "")).casefold(): model
        for model in previous
        if isinstance(model, dict) and model.get("model_id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for snapshot in fresh:
        key = snapshot["model_id"].casefold()
        old = old_by_id.get(key)
        if old:
            row = dict(old)
            row.update(
                {
                    "provider": "modellix",
                    "model_id": snapshot["model_id"],
                    "display_name": snapshot["display_name"],
                    "input_modalities": snapshot["input_modalities"],
                    "output_modalities": snapshot["output_modalities"],
                    "supports_vision": snapshot["supports_vision"],
                }
            )
            extra = dict(old.get("extra") or {})
            extra.update(snapshot["extra"])
            extra["checked_at"] = checked_at
            row["extra"] = extra
        else:
            row = snapshot
            row["extra"]["checked_at"] = checked_at
        seen.add(key)
        merged.append(row)
    # Retain old routes not present in the current docs snapshot; absence is
    # recorded for review but is not interpreted as a deprecation signal.
    for old in previous:
        if not isinstance(old, dict):
            continue
        key = str(old.get("model_id", "")).casefold()
        if key and key not in seen:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra["not_listed_in_current_docs"] = True
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(fresh: list[dict], skipped: list[str] | None = None, *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models = merge_catalog(fresh, previous, checked_at)
    if not models:
        raise ValueError("refusing to write an empty Modellix media catalog")
    DATA.write_text(json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    skipped_text = ", ".join(skipped or []) or "none"
    print(f"modellix_media.json: refreshed {len(fresh)} classifiable records; total={len(models)}")
    return len(fresh)


def main() -> None:
    fresh, skipped = parse_catalog_index(fetch_index())
    update_catalog(fresh, skipped)


if __name__ == "__main__":
    main()
