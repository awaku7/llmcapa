"""Scrape HuggingFace model catalog via API.

Usage:
    python scripts/_scrape_huggingface.py [--save] [--min-downloads N]

The HuggingFace API uses cursor-based pagination. This script collects popular
models across all pipeline tasks and saves them to huggingface.json.

Note on SSR:
    HuggingFace's web UI (huggingface.co/models) is SSR with standard URL
    pagination (?p=0..99). However, the official REST API at
    /api/models provides cursor-based access to ALL models without the
    SSR limitation.

Output format (huggingface.json):
    {
        "models": [
            {
                "provider": "huggingface",
                "model_id": "org/model-name",
                "display_name": "org/model-name",
                "context_window": 0,       # unknown unless read from model config
                "max_output_tokens": 2048, # default
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
                "supports_function_calling": null,
                "supports_vision": true,
                "pipeline_tag": "image-text-to-text",
                "downloads": 123456,
                "likes": 789
            }
        ]
    }
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

API_BASE = "https://huggingface.co/api/models"
DEFAULT_MIN_DOWNLOADS = 5000  # skip models with fewer downloads
BATCH_SIZE = 500  # max per API call
MAX_RETRIES = 5
MAX_BACKOFF_SECONDS = 60.0


def _retry_delay(retry_after: str | None, retry_index: int) -> float:
    """Exponential retry delay, honoring a longer server Retry-After value."""
    delay = min(2.0**retry_index, MAX_BACKOFF_SECONDS)
    if not retry_after:
        return delay
    try:
        server_delay = max(0.0, float(retry_after))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(retry_after)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            server_delay = max(
                0.0, (retry_at - datetime.now(timezone.utc)).total_seconds()
            )
        except (TypeError, ValueError, OverflowError):
            server_delay = 0.0
    return max(delay, server_delay)


def fetch_models(min_downloads: int) -> list:
    """Fetch popular models across all HF tasks with cursor pagination.

    Uses the full URL from the Link header to avoid cursor encoding issues.
    """
    models = []
    next_url = None
    page = 0
    session = requests.Session()

    # Initial request (no cursor)
    params = {
        "sort": "downloads",
        "direction": -1,
        "limit": BATCH_SIZE,
    }

    try:
        while True:
            retry_index = 0
            while True:
                try:
                    if next_url:
                        resp = session.get(next_url, timeout=30)
                    else:
                        resp = session.get(API_BASE, params=params, timeout=30)
                except requests.RequestException as exc:
                    if retry_index >= MAX_RETRIES:
                        raise RuntimeError(
                            f"HuggingFace request failed at page {page}: {exc}"
                        ) from exc
                    delay = _retry_delay(None, retry_index)
                    print(
                        f"  Retry {retry_index + 1}/{MAX_RETRIES} in {delay:g}s "
                        f"after request error at page {page}",
                        flush=True,
                    )
                    time.sleep(delay)
                    retry_index += 1
                    continue

                if resp.status_code == 200:
                    break
                if resp.status_code in {429, 500, 502, 503, 504} and (
                    retry_index < MAX_RETRIES
                ):
                    delay = _retry_delay(
                        resp.headers.get("Retry-After"), retry_index
                    )
                    print(
                        f"  Retry {retry_index + 1}/{MAX_RETRIES} in {delay:g}s "
                        f"after HTTP {resp.status_code} at page {page}",
                        flush=True,
                    )
                    time.sleep(delay)
                    retry_index += 1
                    continue
                raise RuntimeError(
                    f"HuggingFace API returned HTTP {resp.status_code} at page {page}: "
                    f"{resp.text[:200]}"
                )

            batch = resp.json()
            if not batch:
                break

            filtered = [m for m in batch if m.get("downloads", 0) >= min_downloads]
            models.extend(filtered)
            page += 1
            print(
                f"  Page {page}: got {len(batch)} models "
                f"({len(filtered)} >= {min_downloads} downloads), total={len(models)}",
                flush=True,
            )

            # The API sorts descending by downloads. Once the last row in a page
            # is below the threshold, no later page can contribute a model.
            boundary_downloads = int(batch[-1].get("downloads") or 0)
            if boundary_downloads < min_downloads:
                print(
                    f"  Download threshold reached ({boundary_downloads} < "
                    f"{min_downloads}); stopping pagination.",
                    flush=True,
                )
                break

            link_header = resp.headers.get("Link", "")
            match = re.search(r'<([^>]+)>\s*;\s*rel="next"', link_header)
            if match:
                next_url = match.group(1)
            else:
                print("  No more pages.", flush=True)
                break

            time.sleep(0.3)
    finally:
        session.close()
    return models


def convert_to_catalog_format(raw_models: list) -> list:
    """Convert HF API response to our catalog format."""
    results = []
    for m in raw_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        pipeline_tag = m.get("pipeline_tag")

        # Determine modalities from HuggingFace's task metadata, not model names.
        metadata = {str(pipeline_tag).lower()}
        metadata.update(str(tag).lower() for tag in (m.get("tags") or []))
        input_mods, output_mods = _modalities_for_metadata(metadata)
        supports_vision = "image" in input_mods

        entry = {
            "provider": "huggingface",
            "model_id": model_id,
            "display_name": model_id,
            "context_window": 0,
            "max_output_tokens": 2048,
            "input_modalities": input_mods,
            "output_modalities": output_mods,
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_streaming": None,
            "supports_chat_completion": None,
            "supports_responses_api": None,
            "supports_vision": supports_vision,
            "pipeline_tag": pipeline_tag,
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "aliases": [model_id.rsplit("/", 1)[-1]] if "/" in model_id else [],
            "license_type": next(
                (
                    str(tag).split(":", 1)[1]
                    for tag in (m.get("tags") or [])
                    if str(tag).lower().startswith("license:")
                ),
                "unknown",
            ),
            "extra": {"huggingface_tags": list(m.get("tags") or [])},
        }
        results.append(entry)

    return results


def _modalities_for_metadata(metadata: set[str]) -> tuple[list[str], list[str]]:
    """Infer modalities only when supported by HF task/tag metadata."""
    input_tasks = {
        "text": {
            "text-generation",
            "text2text-generation",
            "text-to-image",
            "text-to-video",
            "text-to-speech",
            "text-to-audio",
            "text-classification",
            "token-classification",
            "question-answering",
            "image-text-to-text",
            "visual-question-answering",
            "audio-text-to-text",
            "video-text-to-text",
            "summarization",
            "translation",
            "fill-mask",
            "feature-extraction",
            "sentence-similarity",
            "zero-shot-classification",
            "table-question-answering",
        },
        "image": {
            "image-text-to-text",
            "visual-question-answering",
            "image-to-text",
            "image-classification",
            "image-feature-extraction",
            "image-to-image",
            "image-to-video",
            "object-detection",
            "image-segmentation",
            "depth-estimation",
            "zero-shot-image-classification",
            "image-to-3d",
        },
        "audio": {
            "automatic-speech-recognition",
            "audio-classification",
            "audio-to-audio",
            "audio-to-text",
            "audio-text-to-text",
            "voice-activity-detection",
            "audio-matching",
        },
        "video": {
            "video-classification",
            "zero-shot-video-classification",
            "video-text-to-text",
            "video-to-video",
        },
    }
    inputs = [modality for modality, tasks in input_tasks.items() if metadata & tasks]
    outputs: list[str] = []
    if metadata & {
        "text-generation",
        "text2text-generation",
        "image-text-to-text",
        "visual-question-answering",
        "image-to-text",
        "automatic-speech-recognition",
        "audio-to-text",
        "audio-text-to-text",
        "text-classification",
        "token-classification",
        "question-answering",
        "summarization",
        "translation",
        "fill-mask",
        "sentence-similarity",
        "zero-shot-classification",
        "table-question-answering",
        "image-classification",
        "object-detection",
        "image-segmentation",
        "depth-estimation",
        "video-classification",
        "zero-shot-video-classification",
        "video-text-to-text",
    }:
        outputs.append("text")
    if metadata & {
        "feature-extraction",
        "image-feature-extraction",
        "audio-feature-extraction",
    }:
        outputs.append("embedding")
    if metadata & {"text-to-image", "image-to-image"}:
        outputs.append("image")
    if metadata & {"text-to-video", "image-to-video", "video-to-video"}:
        outputs.append("video")
    if metadata & {
        "text-to-speech",
        "text-to-audio",
        "text-to-speech-generation",
        "text-to-audio-generation",
        "unconditional-audio-generation",
        "audio-to-audio",
    }:
        outputs.append("audio")
    # HF has tasks with modality-specific tags not represented in the mapping.
    # Do not silently label unknown tasks as text-only.
    if not inputs and "text" in metadata:
        inputs.append("text")
    return list(dict.fromkeys(inputs)), list(dict.fromkeys(outputs))


def retain_unlisted_models(current: list[dict], previous: list[dict]) -> list[dict]:
    """Preserve prior curated metadata while refreshing the HF model inventory."""
    previous_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    merged: list[dict] = []
    seen: set[str] = set()
    for current_row in current:
        if not isinstance(current_row, dict) or not current_row.get("model_id"):
            continue
        row = dict(current_row)
        key = str(row["model_id"]).casefold()
        old = previous_by_id.get(key)
        if old:
            for field in ("input_modalities", "output_modalities", "aliases"):
                now = row.get(field) if isinstance(row.get(field), list) else []
                before = old.get(field) if isinstance(old.get(field), list) else []
                row[field] = list(dict.fromkeys([*now, *before]))
            if not row.get("context_window") and old.get("context_window"):
                row["context_window"] = old["context_window"]
            if row.get("max_output_tokens") == 2048 and "max_output_tokens" in old:
                row["max_output_tokens"] = old["max_output_tokens"]
            if row.get("license_type") in (None, "", "unknown") and old.get(
                "license_type"
            ):
                row["license_type"] = old["license_type"]
            old_extra = old.get("extra") if isinstance(old.get("extra"), dict) else {}
            current_extra = (
                row.get("extra") if isinstance(row.get("extra"), dict) else {}
            )
            extra = dict(old_extra)
            extra.update(current_extra)
            extra.pop("not_in_current_update_selection", None)
            row["extra"] = extra
        merged.append(row)
        seen.add(key)

    retained = 0
    for old in previous:
        if not isinstance(old, dict) or not old.get("model_id"):
            continue
        key = str(old["model_id"]).casefold()
        if key in seen:
            continue
        row = dict(old)
        raw_extra = row.get("extra")
        extra = dict(raw_extra) if isinstance(raw_extra, dict) else {}
        extra["not_in_current_update_selection"] = True
        row["extra"] = extra
        merged.append(row)
        seen.add(key)
        retained += 1
    print(f"Retained {retained} prior models outside the current download threshold")
    return merged


def main():
    save = "--save" in sys.argv
    min_downloads = DEFAULT_MIN_DOWNLOADS

    for arg in sys.argv:
        if arg.startswith("--min-downloads="):
            try:
                min_downloads = int(arg.split("=")[1])
            except ValueError:
                pass

    print(
        f"Fetching HuggingFace models (all pipeline tasks, min_downloads={min_downloads})..."
    )
    raw = fetch_models(min_downloads)
    print(f"\nTotal raw models fetched: {len(raw)}")

    catalog = convert_to_catalog_format(raw)
    print(f"Converted to catalog format: {len(catalog)} models")

    # Deduplicate by model_id
    seen = set()
    unique = []
    for m in catalog:
        if m["model_id"] not in seen:
            seen.add(m["model_id"])
            unique.append(m)
    print(f"Unique models: {len(unique)}")

    if not unique:
        raise RuntimeError(
            "HuggingFace API returned no models; refusing to create a catalog "
            "with a fabricated fallback model"
        )
    output = {"models": unique}

    if save:
        proj_root = Path(__file__).resolve().parent.parent
        out_path = proj_root / "src" / "llmcapa" / "data" / "huggingface.json"
        previous = []
        if out_path.exists():
            previous_data = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(previous_data, dict) and isinstance(
                previous_data.get("models"), list
            ):
                previous = previous_data["models"]
        output["models"] = retain_unlisted_models(unique, previous)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(output['models'])} models to {out_path}")
    else:
        print("\nSample entries:")
        for m in unique[:3]:
            print(
                f"  {m['model_id']} (pipeline={m['pipeline_tag']}, ctx={m['context_window']}, downloads={m['downloads']})"
            )


if __name__ == "__main__":
    main()
