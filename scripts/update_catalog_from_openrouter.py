"""Refresh bundled provider catalogs from a captured OpenRouter model snapshot."""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "llmcapa" / "data"
SNAPSHOT = ROOT / "_scratch_openrouter_models.json"

# Known client-facing names used by uag and compatibility tests.
ALIASES = {
    ("meta-llama", "llama-4-scout"): ["Llama-4-Scout-17B-16E"],
    ("meta-llama", "llama-4-maverick"): ["Llama-4-Maverick-17B-128E"],
    ("cohere", "command-a"): ["cohere-command-a", "command-a"],
    ("mistralai", "mistral-large-2512"): ["Mistral-Large-3"],
    ("mistralai", "ministral-3b-2512"): ["Ministral-3B"],
}


def map_record(r: dict) -> dict:
    model_id = r["id"]
    prefix, native_id = model_id.split("/", 1)
    arch = r.get("architecture") or {}
    params = set(r.get("supported_parameters") or [])
    top = r.get("top_provider") or {}
    pricing = r.get("pricing") or {}
    prompt = float(pricing.get("prompt") or 0)
    completion = float(pricing.get("completion") or 0)
    aliases = [model_id.lower()]
    aliases.extend(ALIASES.get((prefix, native_id), []))
    return {
        "provider": prefix,
        "model_id": model_id,
        "display_name": r.get("name", model_id),
        "context_window": int(r.get("context_length") or 0),
        "max_output_tokens": int(top.get("max_completion_tokens") or 0),
        "input_modalities": arch.get("input_modalities") or ["text"],
        "output_modalities": arch.get("output_modalities") or ["text"],
        "supports_function_calling": bool({"tools", "function_calling"} & params),
        "supports_json_mode": bool({"response_format", "structured_outputs", "json_mode"} & params),
        "supports_json_schema": True if "structured_outputs" in params else None,
        "supports_streaming": True,
        "supports_vision": "image" in (arch.get("input_modalities") or []),
        "supports_reasoning": bool({"reasoning", "include_reasoning"} & params),
        "supports_chat_completion": True,
        "supports_responses_api": True,
        "supports_reasoning_effort": "reasoning_effort" in params,
        "supports_thinking_budget": "thinking" in params or "thinking_budget" in params,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": arch.get("tokenizer") or "",
        "knowledge_cutoff": r.get("knowledge_cutoff"),
        "deprecated": False,
        "aliases": aliases,
        "license_type": "unknown",
        "pricing": {"input_per_1m": prompt * 1_000_000, "output_per_1m": completion * 1_000_000, "currency": "USD"},
    }


def load_models(path: Path) -> list[dict]:
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        request = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"User-Agent": "llmcapa-catalog-updater/0.5"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.loads(response.read().decode("utf-8"))
    return raw.get("data", raw)


def load_web_models(prefix: str = "") -> list[dict]:
    """Discover models from OpenRouter's frontend catalog.

    The public models page uses this JSON endpoint. It is used as a
    supplementary discovery source; the regular API snapshot remains the
    authoritative source when both sources contain the same model ID.
    """
    query = f"&q={quote(prefix)}" if prefix else ""
    url = "https://openrouter.ai/api/frontend/v1/models/find?active=true&fmt=cards" + query
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "llmcapa-catalog-updater/0.5",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"warning: failed to read OpenRouter web catalog for {prefix}: {exc}", file=sys.stderr)
        return []

    models = (payload.get("data") or {}).get("models") or []
    records = []
    for model in models:
        model_id = model.get("slug") or ""
        endpoint = model.get("endpoint") or {}
        if prefix and not model_id.startswith(prefix + "/"):
            continue
        pricing = endpoint.get("pricing") or {}
        records.append({
            "id": model_id,
            "name": model.get("name") or model_id,
            "context_length": model.get("context_length") or 0,
            "top_provider": {"max_completion_tokens": endpoint.get("max_completion_tokens") or 0},
            "architecture": {
                "input_modalities": model.get("input_modalities") or ["text"],
                "output_modalities": model.get("output_modalities") or ["text"],
                "tokenizer": "",
            },
            "pricing": {
                "prompt": pricing.get("prompt") or "0",
                "completion": pricing.get("completion") or "0",
            },
            "supported_parameters": endpoint.get("supported_parameters") or [],
            "knowledge_cutoff": model.get("knowledge_cutoff"),
        })
    return records


def main() -> None:
    records = load_models(SNAPSHOT)
    grouped: dict[str, list[dict]] = {}
    for r in records:
        model_id = r.get("id", "")
        if "/" not in model_id or model_id.startswith("~"):
            continue
        prefix = model_id.split("/", 1)[0]
        grouped.setdefault(prefix, []).append(map_record(r))

    # Supplement API discovery with public model pages. API records remain
    # authoritative; web-only records are added only when their IDs are absent.
    for prefix in sorted(grouped):
        api_ids = {entry["model_id"] for entry in grouped[prefix]}
        for web_record in load_web_models(prefix):
            if web_record["id"] not in api_ids:
                grouped[prefix].append(map_record(web_record))

    # Keep provider catalogs isolated; only the OpenRouter aggregate is refreshed.
    updates: dict[str, int] = {}

    # Keep the aggregate OpenRouter catalog in sync with the public frontend
    # catalog as well. This includes models visible on /models that are not
    # present in the regular API snapshot.
    openrouter_path = DATA_DIR / "openrouter.json"
    openrouter_payload = json.loads(openrouter_path.read_text(encoding="utf-8"))
    openrouter_existing = openrouter_payload.get("models", [])
    openrouter_by_id = {
        e.get("model_id").lower(): e
        for e in openrouter_existing
        if e.get("model_id")
    }
    # The API snapshot is authoritative for exact IDs; frontend-only records
    # are then added as a fallback.
    for entries in grouped.values():
        for entry in entries:
            openrouter_by_id[entry["model_id"].lower()] = entry
    for web_record in load_web_models():
        entry = map_record(web_record)
        openrouter_by_id.setdefault(entry["model_id"].lower(), entry)
    openrouter_merged = sorted(openrouter_by_id.values(), key=lambda e: e["model_id"].lower())
    openrouter_path.write_text(
        json.dumps({"models": openrouter_merged}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    updates["openrouter.json"] = len(openrouter_merged)

    print(json.dumps(updates, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
