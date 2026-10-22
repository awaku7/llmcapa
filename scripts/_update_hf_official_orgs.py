"""Refresh HF-publisher catalogs from paginated official organization inventories.

These provider catalogs are publisher/model repositories, not hosted inference
APIs. Model IDs are synchronized from the Hugging Face model API. We retain
curated capability data for known IDs and leave specs unknown for newly found
repositories unless the official API supplies an explicit task tag.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
LOG = ROOT / "provider_update_log.md"
API = "https://huggingface.co/api/models"
PAGE_LIMIT = 100
PAGE_CAP = 100
ORGS = {
    "allenai": "allenai",
    "anthracite-org": "anthracite-org",
    "arcee-ai": "arcee-ai",
    "cognitivecomputations": "cognitivecomputations",
    "deepcogito": "deepcogito",
    "gryphe": "Gryphe",
    "inclusionai": "inclusionAI",
    "kwaipilot": "Kwai-Kolors",
    "mancer": "Mancer",
    "meituan": "meituan-longcat",
    "nex-agi": "Nex-AGI",
    "nousresearch": "NousResearch",
    "perceptron": "PERCEPTRON",
    "sao10k": "Sao10K",
    "thedrummer": "TheDrummer",
    "undi95": "undi95",
}

TASK_MODALITIES: dict[str, tuple[list[str], list[str]]] = {
    "text-generation": (["text"], ["text"]),
    "conversational": (["text"], ["text"]),
    "image-text-to-text": (["text", "image"], ["text"]),
    "visual-question-answering": (["text", "image"], ["text"]),
    "image-to-text": (["image"], ["text"]),
    "text-to-image": (["text"], ["image"]),
    "image-to-image": (["text", "image"], ["image"]),
    "automatic-speech-recognition": (["audio"], ["text"]),
    "audio-to-audio": (["audio"], ["audio"]),
    "text-to-speech": (["text"], ["audio"]),
    "text-to-audio": (["text"], ["audio"]),
    "feature-extraction": (["text"], ["embedding"]),
    "sentence-similarity": (["text"], ["embedding"]),
    "text-ranking": (["text"], ["rerank"]),
}


def _fetch_json(url: str) -> tuple[object, str | None]:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "llmcapa-official-updater/1.0"},
    )
    with urlopen(request, timeout=45) as response:
        payload = json.loads(response.read(8_000_000).decode("utf-8", "replace"))
        return payload, response.headers.get("Link")


def fetch_models(org: str) -> list[dict]:
    """Fetch every model repository listed under a publisher account."""
    url = f"{API}?author={quote(org)}&limit={PAGE_LIMIT}&full=true"
    records: dict[str, dict] = {}
    for page in range(PAGE_CAP):
        payload, link = _fetch_json(url)
        if not isinstance(payload, list):
            raise ValueError(f"Hugging Face returned a non-list response for {org}")
        for item in payload:
            if isinstance(item, dict) and item.get("modelId"):
                records[str(item["modelId"])] = item
        next_link = re.search(r'<([^>]+)>\s*;\s*rel="next"', link or "")
        if not next_link:
            break
        url = next_link.group(1)
        time.sleep(0.15)
    else:
        raise RuntimeError(f"Hugging Face pagination exceeded {PAGE_CAP} pages for {org}")
    if not records:
        raise RuntimeError(f"Hugging Face returned no models for {org}; refusing to empty the catalog")
    return [records[key] for key in sorted(records, key=str.casefold)]


def _new_model(provider: str, item: dict) -> dict:
    model_id = str(item["modelId"]).strip()
    pipeline = str(item.get("pipeline_tag") or "").strip().lower()
    inputs, outputs = TASK_MODALITIES.get(pipeline, ([], []))
    vision = True if "image" in inputs else None
    return {
        "provider": provider,
        "model_id": model_id,
        "display_name": model_id,
        "context_window": 0,
        "max_output_tokens": 0,
        "input_modalities": inputs,
        "output_modalities": outputs,
        "supports_function_calling": None,
        "supports_json_mode": None,
        "supports_json_schema": None,
        "supports_streaming": None,
        "supports_vision": vision,
        "supports_reasoning": None,
        "supports_chat_completion": None,
        "supports_responses_api": None,
        "pricing": None,
        "deprecated": False,
        "aliases": [],
        "license_type": None,
    }


def _update_row(provider: str, org: str, item: dict, checked_at: str, old: dict | None) -> dict:
    model_id = str(item["modelId"]).strip()
    row = dict(old) if old else _new_model(provider, item)
    # Preserve hand-verified model specs for existing IDs; the API's task tag
    # is stored as evidence and is used to initialize only new rows.
    row["provider"] = provider
    row["model_id"] = model_id
    row.setdefault("display_name", model_id)
    if provider == "inclusionai" and model_id.casefold() in {
        "inclusionai/ming-3.0-audio-flash",
        "inclusionai/ming-3.0-audio-tiny",
    }:
        # Official model cards describe audio/text inputs and outputs; the
        # Hugging Face text-to-speech pipeline tag is only a subset.
        row["input_modalities"] = ["text", "audio"]
        row["output_modalities"] = ["text", "audio"]
    extra = dict(row.get("extra") or {})
    card = item.get("cardData") if isinstance(item.get("cardData"), dict) else {}
    tags = sorted(str(tag) for tag in item.get("tags", []) if isinstance(tag, str))
    extra.update(
        {
            "official_source": f"https://huggingface.co/{model_id}",
            "official_source_checked_at": checked_at,
            "official_spec_refresh": "official_huggingface_model_inventory",
            "official_hf_org": org,
            "official_hf_pipeline_tag": str(item.get("pipeline_tag") or "") or None,
            "official_hf_tags": tags,
            "official_hf_downloads": item.get("downloads"),
            "official_hf_likes": item.get("likes"),
            "official_hf_license": card.get("license"),
            "official_hf_current": True,
        }
    )
    row["extra"] = extra
    return row


def merge_inventory(provider: str, org: str, records: list[dict], previous: list[dict], checked_at: str) -> tuple[list[dict], int]:
    """Merge live repository IDs while retaining curated specs and history."""
    old_by_id = {
        str(model.get("model_id", "")).casefold(): model
        for model in previous
        if isinstance(model, dict) and model.get("model_id")
    }
    seen: set[str] = set()
    models = []
    for item in records:
        key = str(item["modelId"]).casefold()
        models.append(_update_row(provider, org, item, checked_at, old_by_id.get(key)))
        seen.add(key)
    retained = 0
    for old in previous:
        if not isinstance(old, dict):
            continue
        key = str(old.get("model_id", "")).casefold()
        if key and key not in seen:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra.update({"official_hf_current": False, "not_listed_in_current_hf_inventory_at": checked_at})
            row["extra"] = extra
            models.append(row)
            retained += 1
    return models, retained


def update_provider(provider: str, org: str, *, checked_at: str | None = None) -> tuple[int, int]:
    path = DATA / f"{provider}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    records = fetch_models(org)
    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    models, retained = merge_inventory(provider, org, records, previous, checked_at)
    path.write_text(
        json.dumps({**data, "models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(records), retained


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider",
        choices=sorted(ORGS),
        help="refresh one provider's full Hugging Face model-repository inventory",
    )
    args = parser.parse_args()
    checked_at = datetime.now(timezone.utc).date().isoformat()
    selected = {args.provider: ORGS[args.provider]} if args.provider else ORGS
    results = []
    for provider, org in selected.items():
        count, retained = update_provider(provider, org, checked_at=checked_at)
        results.append((provider, count, retained))
    lines = [
        f"\n## Hugging Face organization model-inventory refresh ({checked_at})\n\n",
        "- Source: official Hugging Face model API (`huggingface.co/api/models`), including Link-header pagination.\n",
        "- Model repository IDs are synchronized; model-native context, pricing, and API features are preserved or unknown.\n",
        "- Historical records absent from the current inventory are retained and marked not-listed.\n",
    ]
    lines.extend(
        f"- {provider}: {count} live model repositories; {retained} historical records retained.\n"
        for provider, count, retained in results
    )
    LOG.write_text(LOG.read_text(encoding="utf-8") + "".join(lines), encoding="utf-8")
    print("; ".join(f"{provider}={count} live/{retained} retained" for provider, count, retained in results))


if __name__ == "__main__":
    main()
