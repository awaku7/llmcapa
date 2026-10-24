"""Refresh Morph's complete model inventory from its official model API."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src" / "llmcapa" / "data" / "morph.json"
SOURCE = "https://www.morphllm.com/api/models/json"
BASE_URL = "https://api.morphllm.com/v1"


def fetch_inventory() -> dict:
    request = Request(
        SOURCE,
        headers={"Accept": "application/json", "User-Agent": "llmcapa-provider-updater/1.0"},
    )
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read(8_000_000).decode("utf-8", "replace"))
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise ValueError("Morph model API returned an unexpected catalog structure")
    return payload


def _quantity_value(value: object) -> int:
    if not isinstance(value, dict):
        return 0
    try:
        amount = float(value.get("value", 0))
    except (TypeError, ValueError):
        return 0
    unit = str(value.get("unit", "token")).casefold()
    if unit in {"k", "ktoken", "k_tokens"}:
        amount *= 1_000
    elif unit in {"m", "mtoken", "m_tokens"}:
        amount *= 1_000_000
    return int(amount)


def _price_for(modalities: list, kind: str) -> float | None:
    for modality in modalities:
        if not isinstance(modality, dict):
            continue
        for price in modality.get("pricing", []):
            if isinstance(price, dict) and price.get("type") == kind:
                try:
                    return float(price["cost_usd"]) * 1_000_000
                except (KeyError, TypeError, ValueError):
                    return None
    return None


def _normalize_item(item: dict, checked_at: str) -> dict:
    model_id = str(item.get("id", "")).strip()
    if not model_id:
        raise ValueError("Morph model entry is missing id")
    input_entries = item.get("input_modalities") or []
    output_entries = item.get("output_modalities") or []
    inputs = sorted(
        {str(row["type"]).casefold() for row in input_entries if isinstance(row, dict) and row.get("type")}
    )
    outputs = sorted(
        {str(row["type"]).casefold() for row in output_entries if isinstance(row, dict) and row.get("type")}
    )
    text_input = next(
        (row for row in input_entries if isinstance(row, dict) and row.get("type") == "text"),
        {},
    )
    text_output = next(
        (row for row in output_entries if isinstance(row, dict) and row.get("type") == "text"),
        {},
    )
    params = text_output.get("supported_parameters") or {}
    if not isinstance(params, dict):
        params = {}
    has_json = isinstance(params.get("json_mode"), dict) and params["json_mode"].get("type") == "boolean"
    has_schema = isinstance(params.get("structured_outputs"), dict) and params["structured_outputs"].get("type") == "boolean"
    has_tools = isinstance(params.get("tools"), dict) and params["tools"].get("type") == "boolean"
    has_reasoning = isinstance(params.get("reasoning"), dict) and params["reasoning"].get("type") == "boolean"
    input_price = _price_for(input_entries, "prompt")
    output_price = _price_for(output_entries, "completion")
    pricing = None
    if input_price is not None and output_price is not None:
        pricing = {"input_per_1m": input_price, "output_per_1m": output_price, "currency": "USD"}
    extra = {
        "official_source": SOURCE,
        "official_source_checked_at": checked_at,
        "official_spec_refresh": "official_morph_model_api",
        "base_url": BASE_URL,
        "description": item.get("description"),
        "hugging_face_id": item.get("hugging_face_id"),
        "quantization": item.get("quantization"),
        "created": item.get("created"),
        "is_ready": item.get("is_ready"),
    }
    cache_input = _price_for(input_entries, "cached_prompt")
    if cache_input is not None:
        extra["cached_input_per_1m"] = cache_input
    return {
        "provider": "morph",
        "model_id": model_id,
        "display_name": str(item.get("name") or model_id),
        "context_window": _quantity_value((text_input.get("supported_inputs") or {}).get("max_context_length")),
        "max_output_tokens": _quantity_value(text_output.get("max_length")),
        "input_modalities": inputs,
        "output_modalities": outputs,
        "supports_function_calling": True if has_tools else None,
        "supports_json_mode": True if has_json else None,
        "supports_json_schema": True if has_schema else None,
        "supports_streaming": text_output.get("streaming"),
        "supports_vision": "image" in inputs,
        "supports_reasoning": True if has_reasoning else None,
        "supports_chat_completion": True,
        "supports_responses_api": None,
        "pricing": pricing,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
        "extra": extra,
    }


def parse_inventory(payload: dict, *, checked_at: str = "2026-01-01") -> list[dict]:
    """Normalize only the official Morph endpoint fields; ignore third-party metadata."""
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise ValueError("Morph model API has no data array")
    result = []
    seen: set[str] = set()
    for item in rows:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        model = _normalize_item(item, checked_at)
        key = model["model_id"].casefold()
        if key in seen:
            continue
        if item.get("is_ready") is False:
            continue
        result.append(model)
        seen.add(key)
    if not result:
        raise ValueError("Morph model API returned no usable model IDs; refusing to clear catalog")
    return result


def merge_catalog(current: list[dict], previous: list[dict]) -> list[dict]:
    old_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    seen: set[str] = set()
    merged: list[dict] = []
    for snapshot in current:
        key = snapshot["model_id"].casefold()
        old = old_by_id.get(key)
        row = dict(old or {})
        row.update(snapshot)
        extra = dict(old.get("extra") or {}) if old else {}
        extra.update(snapshot["extra"])
        row["extra"] = extra
        merged.append(row)
        seen.add(key)
    for old in previous:
        key = str(old.get("model_id", "")).casefold() if isinstance(old, dict) else ""
        if key and key not in seen:
            row = dict(old)
            extra = dict(row.get("extra") or {})
            extra.update({"official_source_checked_at": current[0]["extra"]["official_source_checked_at"], "official_morph_current": False})
            row["extra"] = extra
            merged.append(row)
    return merged


def update_catalog(current: list[dict], *, checked_at: str | None = None) -> int:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    previous = data.get("models") or []
    merged = merge_catalog(current, previous)
    DATA.write_text(json.dumps({**data, "models": merged}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    checked_at = checked_at or current[0]["extra"]["official_source_checked_at"]
    print(f"morph.json: refreshed {len(current)} official model IDs; total={len(merged)}")
    return len(current)


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    update_catalog(parse_inventory(fetch_inventory(), checked_at=checked_at), checked_at=checked_at)


if __name__ == "__main__":
    main()
