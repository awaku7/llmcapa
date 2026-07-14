"""Update novita.json with live data from Novita AI API (no API key required).

Usage:
    python scripts/_update_novita_from_api.py

This fetches https://api.novita.ai/openai/v1/models and merges the results
into novita.json. New models are added; existing models' pricing and metadata
are updated. Test models and entries with context_window=0 are skipped.

Supports --dry-run to preview changes without writing.
"""
import json
import os
import ssl
import sys
import urllib.request

# ---- paths ----
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(SRC_DIR, "src", "llmcapa", "data")
NOVITA_JSON = os.path.join(DATA_DIR, "novita.json")

# site-packages fallback (auto-detected)
INSTALLED_CANDIDATES = [
    os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages", "llmcapa", "data"),
    os.path.join(os.path.dirname(os.path.dirname(sys.executable)), "Lib", "site-packages", "llmcapa", "data"),
]

API_URL = "https://api.novita.ai/openai/v1/models"


def fetch_models() -> list[dict]:
    """Fetch all models from Novita AI API."""
    ctx = ssl._create_unverified_context()
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )
    with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("data", [])


def api_to_entry(m: dict) -> dict | None:
    """Convert an API record to a novita.json entry. Returns None if skipped."""
    mid = m["id"]
    key = mid.lower()

    # Skip test models
    if "test" in key:
        return None
    # Skip models with zero context window
    if m.get("context_size", 0) == 0:
        return None

    features = m.get("features", []) or []
    input_mods = m.get("input_modalities", ["text"]) or ["text"]
    output_mods = m.get("output_modalities", ["text"]) or ["text"]

    # Pricing conversion: Novita API uses 1/100,000 USD units
    inp_price = m.get("input_token_price_per_m")
    out_price = m.get("output_token_price_per_m")
    pricing = None
    if inp_price is not None and out_price is not None:
        pricing = {
            "input_per_1m": round(inp_price / 100000, 6),
            "output_per_1m": round(out_price / 100000, 6),
            "currency": "USD",
        }

    return {
        "provider": "novita",
        "model_id": mid,
        "display_name": m.get("display_name", mid),
        "context_window": m.get("context_size", 4096),
        "max_output_tokens": m.get("max_output_tokens", 2048),
        "input_modalities": input_mods,
        "output_modalities": output_mods,
        "supports_function_calling": "function-calling" in features,
        "supports_json_mode": "structured-outputs" in features,
        "supports_streaming": True,
        "supports_vision": "image" in input_mods,
        "supports_reasoning": "reasoning" in features,
        "supports_chat_completion": True,
        "supports_responses_api": False,
        "supports_reasoning_effort": "reasoning" in features,
        "supports_thinking_budget": False,
        "supports_anthropic_api": "anthropic" in (m.get("endpoints", []) or []),
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": pricing,
        "deprecated": m.get("status", 1) != 1,
        "aliases": [mid.lower()],
        "license_type": "api",
    }


def update_novita(dry_run: bool = False) -> dict:
    """Update novita.json from API. Returns summary dict."""
    # Load current bundled data
    with open(NOVITA_JSON, "r", encoding="utf-8") as f:
        bundled = json.load(f)

    existing_map: dict[str, dict] = {m["model_id"].lower(): m for m in bundled["models"]}

    # Fetch from API
    print("Fetching models from Novita AI API...", flush=True)
    api_models = fetch_models()
    print(f"  API returned {len(api_models)} models", flush=True)

    added = 0
    updated = 0
    skipped = 0

    for m in api_models:
        entry = api_to_entry(m)
        if entry is None:
            skipped += 1
            continue

        key = entry["model_id"].lower()
        if key in existing_map:
            # Update pricing and metadata for existing models
            old = existing_map[key]
            changed = False
            for field in ("context_window", "max_output_tokens", "pricing",
                          "supports_function_calling", "supports_json_mode",
                          "supports_streaming", "supports_vision", "supports_reasoning",
                          "deprecated", "display_name", "supports_anthropic_api"):
                if entry.get(field) != old.get(field):
                    old[field] = entry[field]
                    changed = True
            if changed:
                updated += 1
        else:
            existing_map[key] = entry
            added += 1

    # Sort
    new_models = sorted(existing_map.values(), key=lambda x: (x["model_id"].lower()))

    summary = {
        "previous_count": len(bundled["models"]),
        "new_count": len(new_models),
        "added": added,
        "updated": updated,
        "skipped_api": skipped,
    }

    if not dry_run:
        # Write backup
        backup = NOVITA_JSON + ".org"
        if not os.path.exists(backup):
            import shutil
            shutil.copy2(NOVITA_JSON, backup)

        # Write new data
        with open(NOVITA_JSON, "w", encoding="utf-8") as f:
            json.dump({"models": new_models}, f, ensure_ascii=False, indent=2)
        print(f"  Written: {NOVITA_JSON}", flush=True)

        # Try to sync site-packages
        for candidate in INSTALLED_CANDIDATES:
            dst = os.path.join(candidate, "novita.json")
            if os.path.isdir(candidate):
                import shutil
                shutil.copy2(NOVITA_JSON, dst)
                print(f"  Synced: {dst}", flush=True)
                break
    else:
        print("  (dry-run, no files written)", flush=True)

    return summary


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    summary = update_novita(dry_run=dry_run)
    print(f"\nSummary:", flush=True)
    for k, v in summary.items():
        print(f"  {k}: {v}", flush=True)
