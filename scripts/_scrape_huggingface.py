"""Scrape HuggingFace model catalog via API.

Usage:
    python scripts/_scrape_huggingface.py [--save] [--min-downloads N]

The HuggingFace API uses cursor-based pagination. This script collects
text-generation models from the API and saves them to huggingface.json.

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
                "context_window": 4096,    # default, often unknown
                "max_output_tokens": 2048, # default
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_function_calling": false,
                "supports_vision": false,
                "supports_audio_input": false,
                "supports_audio_output": false,
                "pipeline_tag": "text-generation",
                "downloads": 123456,
                "likes": 789
            }
        ]
    }
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

API_BASE = "https://huggingface.co/api/models"
PIPELINE_FILTER = "text-generation"
DEFAULT_MIN_DOWNLOADS = 5000  # skip models with fewer downloads
BATCH_SIZE = 500  # max per API call


def fetch_models(min_downloads: int) -> list:
    """Fetch all text-generation models with cursor-based pagination.

    Uses the full URL from the Link header to avoid cursor encoding issues.
    """
    models = []
    next_url = None
    page = 0

    # Initial request (no cursor)
    params = {
        "pipeline_tag": PIPELINE_FILTER,
        "sort": "downloads",
        "direction": -1,
        "limit": BATCH_SIZE,
    }

    while True:
        if next_url:
            resp = requests.get(next_url, timeout=30)
        else:
            resp = requests.get(API_BASE, params=params, timeout=30)

        if resp.status_code != 200:
            print(f"[ERROR] HTTP {resp.status_code} at page {page}")
            print(f"  Response: {resp.text[:200]}")
            break

        batch = resp.json()
        if not batch:
            break

        # Filter by min downloads
        filtered = [m for m in batch if m.get("downloads", 0) >= min_downloads]
        models.extend(filtered)

        page += 1
        print(f"  Page {page}: got {len(batch)} models ({len(filtered)} >= {min_downloads} downloads), total={len(models)}")

        # Check for next page via Link header
        link_header = resp.headers.get("Link", "")
        match = re.search(r'<([^>]+)>\s*;\s*rel="next"', link_header)
        if match:
            next_url = match.group(1)
        else:
            print("  No more pages.")
            break

        time.sleep(0.3)

    return models


def convert_to_catalog_format(raw_models: list) -> list:
    """Convert HF API response to our catalog format."""
    results = []
    for m in raw_models:
        model_id = m.get("id", "")
        if not model_id:
            continue

        pipeline_tag = m.get("pipeline_tag", PIPELINE_FILTER)

        # Determine modalities based on model id hints
        input_mods = ["text"]
        output_mods = ["text"]
        supports_vision = False
        supports_audio_input = False
        supports_audio_output = False

        lid = model_id.lower()

        if any(kw in lid for kw in ["vl", "vision", "visual", "vlm", "llava", "cogvlm", "qwen-vl", "idefics", "fuyu"]):
            if "text" not in input_mods:
                input_mods.append("image")
            supports_vision = True

        if any(kw in lid for kw in ["whisper", "voice", "speech", "audio", "wav2vec", "hubert"]):
            if "audio" not in input_mods:
                input_mods.append("audio")
            supports_audio_input = True

        if any(kw in lid for kw in ["tts", "vall-e", "bark", "cosyvoice"]):
            if "audio" not in output_mods:
                output_mods.append("audio")
            supports_audio_output = True

        entry = {
            "provider": "huggingface",
            "model_id": model_id,
            "display_name": model_id,
            "context_window": 4096,
            "max_output_tokens": 2048,
            "input_modalities": input_mods,
            "output_modalities": output_mods,
            "supports_function_calling": False,
            "supports_vision": supports_vision,
            "supports_audio_input": supports_audio_input,
            "supports_audio_output": supports_audio_output,
            "pipeline_tag": pipeline_tag,
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
        }
        results.append(entry)

    return results


def main():
    save = "--save" in sys.argv
    min_downloads = DEFAULT_MIN_DOWNLOADS

    for arg in sys.argv:
        if arg.startswith("--min-downloads="):
            try:
                min_downloads = int(arg.split("=")[1])
            except ValueError:
                pass

    print(f"Fetching HuggingFace models (pipeline_tag={PIPELINE_FILTER}, min_downloads={min_downloads})...")
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

    output = {"models": unique}

    if save:
        proj_root = Path(__file__).resolve().parent.parent
        out_path = proj_root / "src" / "llmcapa" / "data" / "huggingface.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)
        print(f"Saved to {out_path}")
    else:
        print(f"\nSample entries:")
        for m in unique[:3]:
            print(f"  {m['model_id']} (pipeline={m['pipeline_tag']}, ctx={m['context_window']}, downloads={m['downloads']})")


if __name__ == "__main__":
    main()
