"""Refresh bundled provider catalogs from a captured OpenRouter model snapshot."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "llmcapa" / "data"
SNAPSHOT = ROOT / "_scratch_openrouter_models.json"

# OpenRouter prefixes which are represented by an existing canonical catalog.
CANONICAL_FILES = {
    "anthropic": "anthropic.json", "deepseek": "deepseek.json", "google": "google.json",
    "meta": "meta.json", "meta-llama": "meta.json", "mistralai": "mistral.json",
    "qwen": "qwen.json", "x-ai": "xai.json", "openai": "openai.json",
    "amazon": "amazon.json", "microsoft": "microsoft.json", "nvidia": "nvidia.json",
    "novita": "novita.json", "moonshotai": "moonshot.json", "xiaomi": "xiaomi.json",
    "sakana": "sakana.json",
}

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
        "supports_streaming": True,
        "supports_vision": "image" in (arch.get("input_modalities") or []),
        "supports_reasoning": bool({"reasoning", "include_reasoning"} & params),
        "supports_chat_completion": True,
        "supports_responses_api": False,
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


def main() -> None:
    records = load_models(SNAPSHOT)
    grouped: dict[str, list[dict]] = {}
    for r in records:
        model_id = r.get("id", "")
        if "/" not in model_id or model_id.startswith("~"):
            continue
        prefix = model_id.split("/", 1)[0]
        grouped.setdefault(prefix, []).append(map_record(r))

    # Add the latest snapshot to canonical files, retaining curated local records.
    updates: dict[str, int] = {}
    for prefix, entries in grouped.items():
        filename = CANONICAL_FILES.get(prefix)
        if filename is None:
            filename = re.sub(r"[^A-Za-z0-9_.-]", "-", prefix) + ".json"
        path = DATA_DIR / filename
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            existing = payload.get("models", payload if isinstance(payload, list) else [])
        else:
            existing = []
        by_id = {e.get("model_id"): e for e in existing if e.get("model_id")}
        for entry in entries:
            # Prefer the latest snapshot for exact OpenRouter IDs.
            by_id[entry["model_id"]] = entry
        merged = sorted(by_id.values(), key=lambda e: e["model_id"].lower())
        path.write_text(json.dumps({"models": merged}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        updates[filename] = len(merged)

    # Add stable aliases for records which are not currently listed by OpenRouter.
    meta_path = DATA_DIR / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))["models"]
    meta.append({
        "provider": "meta-llama", "model_id": "Llama-3.2-90B-Vision-Instruct",
        "display_name": "Llama 3.2 90B Vision Instruct", "context_window": 128000,
        "max_output_tokens": 4096, "input_modalities": ["text", "image"], "output_modalities": ["text"],
        "supports_function_calling": False, "supports_json_mode": True, "supports_streaming": True,
        "supports_vision": True, "supports_reasoning": False, "supports_chat_completion": True,
        "supports_responses_api": False, "supports_reasoning_effort": False, "supports_thinking_budget": False,
        "supports_anthropic_api": False, "supports_google_api": False, "supports_fim": False,
        "tokenizer_name": "Llama3", "knowledge_cutoff": None, "deprecated": False,
        "aliases": ["llama-3.2-90b-vision-instruct"], "license_type": "open",
    })
    # Ensure no duplicate manual entry on reruns.
    seen = set()
    meta = [e for e in meta if not (e.get("model_id") in seen or seen.add(e.get("model_id")))]
    meta_path.write_text(json.dumps({"models": sorted(meta, key=lambda e: e["model_id"].lower())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mistral_path = DATA_DIR / "mistral.json"
    mistral = json.loads(mistral_path.read_text(encoding="utf-8"))["models"]
    for model_id, display, ctx, vision, fc in [
        ("Mistral-Large-3", "Mistral Large 3", 262144, True, True),
        ("Ministral-3B", "Ministral 3B", 131072, False, True),
    ]:
        if not any(e.get("model_id") == model_id for e in mistral):
            mistral.append({"provider": "mistral", "model_id": model_id, "display_name": display,
                "context_window": ctx, "max_output_tokens": 4096, "input_modalities": ["text", "image"] if vision else ["text"],
                "output_modalities": ["text"], "supports_function_calling": fc, "supports_json_mode": True,
                "supports_streaming": True, "supports_vision": vision, "supports_reasoning": False,
                "supports_chat_completion": True, "supports_responses_api": False, "supports_reasoning_effort": False,
                "supports_thinking_budget": False, "supports_anthropic_api": False, "supports_google_api": False,
                "supports_fim": False, "tokenizer_name": "Mistral", "knowledge_cutoff": None,
                "deprecated": False, "aliases": [model_id.lower()], "license_type": "open"})
    mistral_path.write_text(json.dumps({"models": sorted(mistral, key=lambda e: e["model_id"].lower())}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    updates["meta.json"] = len(meta); updates["mistral.json"] = len(mistral)
    print(json.dumps(updates, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
