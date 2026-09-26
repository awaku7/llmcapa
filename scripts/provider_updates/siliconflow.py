"""Refresh SiliconFlow models from its authenticated official model-list API.

The public docs list ``GET /v1/models`` as the model-catalog endpoint. A
SiliconFlow API key is required, so this updater fails closed if
``SILICONFLOW_API_KEY`` is unavailable; it never scrapes arbitrary prose or
falls back to a hand-maintained model manifest.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/siliconflow.json"
LOG = ROOT / "provider_update_log.md"
API_URL = "https://api.siliconflow.com/v1/models"
SOURCE = "https://docs.siliconflow.com/en/api-reference/models/get-model-list"

# Official GET /models filters. We query the unfiltered list plus task/type
# variants because the API response schema itself only guarantees model IDs.
QUERIES = [
    {},
    {"sub_type": "chat"},
    {"sub_type": "embedding"},
    {"sub_type": "reranker"},
    {"sub_type": "text-to-image"},
    {"sub_type": "image-to-image"},
    {"sub_type": "speech-to-text"},
    {"sub_type": "text-to-video"},
    {"type": "text"},
    {"type": "image"},
    {"type": "audio"},
    {"type": "video"},
]


def fetch_models(api_key: str, query: dict[str, str]) -> list[dict]:
    url = API_URL + ("?" + urlencode(query) if query else "")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "llmcapa-official-updater/1.0",
        },
    )
    with urlopen(request, timeout=45) as response:
        payload = json.loads(response.read(4_000_000).decode("utf-8", "replace"))
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError(f"SiliconFlow /models response has no data list for {query}")
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def catalog_rows(responses: list[tuple[dict[str, str], list[dict]]]) -> list[dict]:
    by_id: dict[str, dict] = {}
    for query, models in responses:
        for model in models:
            model_id = str(model["id"]).strip()
            key = model_id.casefold()
            if not key:
                continue
            row = by_id.setdefault(
                key,
                {
                    "provider": "siliconflow",
                    "model_id": model_id,
                    "display_name": model_id,
                    "context_window": 0,
                    "max_output_tokens": 0,
                    "input_modalities": [],
                    "output_modalities": [],
                    "supports_chat_completion": None,
                    "supports_function_calling": None,
                    "supports_json_mode": None,
                    "supports_streaming": None,
                    "supports_vision": None,
                    "supports_reasoning": None,
                    "supports_responses_api": None,
                    "pricing": None,
                    "deprecated": False,
                    "aliases": [],
                    "license_type": "api",
                    "extra": {"source": SOURCE, "catalog_types": [], "catalog_subtypes": []},
                },
            )
            if query.get("type") and query["type"] not in row["extra"]["catalog_types"]:
                row["extra"]["catalog_types"].append(query["type"])
            if query.get("sub_type") and query["sub_type"] not in row["extra"]["catalog_subtypes"]:
                row["extra"]["catalog_subtypes"].append(query["sub_type"])

    for row in by_id.values():
        subtypes = set(row["extra"]["catalog_subtypes"])
        types = set(row["extra"]["catalog_types"])
        if "chat" in subtypes:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["text"]
            row["supports_chat_completion"] = True
        elif "embedding" in subtypes:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["embedding"]
            row["supports_chat_completion"] = False
        elif "reranker" in subtypes:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["rerank"]
            row["supports_chat_completion"] = False
        elif "text-to-image" in subtypes:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["image"]
            row["supports_chat_completion"] = False
        elif "image-to-image" in subtypes:
            row["input_modalities"] = ["text", "image"]
            row["output_modalities"] = ["image"]
            row["supports_vision"] = True
            row["supports_chat_completion"] = False
        elif "speech-to-text" in subtypes:
            row["input_modalities"] = ["audio"]
            row["output_modalities"] = ["text"]
            row["supports_chat_completion"] = False
        elif "text-to-video" in subtypes:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["video"]
            row["supports_chat_completion"] = False
        elif "image" in types:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["image"]
            row["supports_chat_completion"] = False
        elif "audio" in types:
            # The API confirms an audio model, but not its direction.
            row["input_modalities"] = ["audio"]
            row["output_modalities"] = []
            row["supports_chat_completion"] = False
        elif "video" in types:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["video"]
            row["supports_chat_completion"] = False
        elif "text" in types:
            row["input_modalities"] = ["text"]
            row["output_modalities"] = ["text"]
    return sorted(by_id.values(), key=lambda row: row["model_id"].casefold())


def merge_previous(live: list[dict], previous: list[dict]) -> list[dict]:
    old_by_id = {str(row.get("model_id", "")).casefold(): row for row in previous}
    merged: list[dict] = []
    seen: set[str] = set()
    for fresh in live:
        key = fresh["model_id"].casefold()
        old = old_by_id.get(key)
        if old:
            row = dict(old)
            for field, value in fresh.items():
                if field == "extra":
                    row["extra"] = {**(row.get("extra") or {}), **value}
                elif field == "pricing" and value is None:
                    continue
                elif field in {"context_window", "max_output_tokens"} and not value:
                    continue
                elif field.startswith("supports_") and value is None:
                    continue
                elif field in {"input_modalities", "output_modalities"} and not value:
                    continue
                else:
                    row[field] = value
            fresh = row
        merged.append(fresh)
        seen.add(key)

    # The authenticated API may be account-scoped. Retain older records not
    # returned for this key, but clearly label that their availability was not
    # confirmed by the current response rather than deleting them.
    for old in previous:
        key = str(old.get("model_id", "")).casefold()
        if key and key not in seen:
            row = dict(old)
            row.setdefault("extra", {})["not_returned_by_current_api_key"] = True
            merged.append(row)
    return merged


def main() -> None:
    api_key = os.environ.get("SILICONFLOW_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "SILICONFLOW_API_KEY is required for the official authenticated GET /v1/models API; "
            "no page-text fallback is used."
        )

    responses = []
    for query in QUERIES:
        try:
            responses.append((query, fetch_models(api_key, query)))
        except Exception as exc:  # noqa: BLE001
            if not query:
                raise SystemExit(f"SiliconFlow official model-list request failed: {exc}") from exc
            # A failing optional filter must not invalidate a successful base catalog.
            print(f"warning: SiliconFlow filter {query} unavailable: {exc}", flush=True)
    live = catalog_rows(responses)
    if not live:
        raise SystemExit("SiliconFlow official API returned no model IDs; refusing to overwrite catalog")

    current = json.loads(DATA.read_text(encoding="utf-8"))
    previous = current.get("models") or []
    models = merge_previous(live, previous)
    DATA.write_text(json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).date().isoformat()
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## SiliconFlow official model API refresh ({stamp})\n\n"
        + f"- Source: {API_URL} (authenticated; filters: type/sub_type)\n"
        + f"- API model IDs: {len(live)}; retained account-unlisted prior records: {len(models) - len(live)}\n"
        + "- No text scraping or manual model manifest was used.\n",
        encoding="utf-8",
    )
    print(f"siliconflow.json: live IDs={len(live)} total={len(models)}")


if __name__ == "__main__":
    main()
