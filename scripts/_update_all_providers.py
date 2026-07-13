"""Fetch OpenRouter data and update all provider JSON files."""
import json, os, sys, shutil
from datetime import date
from collections import defaultdict

# Provider name mapping: OpenRouter provider -> bundled JSON provider
PROVIDER_MAP = {
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "google": "google",
    "meta-llama": "meta",
    "mistralai": "mistral",
    "qwen": "qwen",
    "x-ai": "xai",
    "openai": "openai",
    "amazon": "amazon",
    "microsoft": "microsoft",
    "nvidia": "nvidia",
    "novita": "novita",
    "moonshot": "moonshot",
    "xiaomi": "xiaomi",
    "sakana": "sakana",
}

# JSON file names per bundled provider
PROVIDER_FILES = {
    "anthropic": "anthropic.json",
    "deepseek": "deepseek.json",
    "google": "google.json",
    "meta": "meta.json",
    "mistral": "mistral.json",
    "qwen": "qwen.json",
    "xai": "xai.json",
    "openai": "openai.json",
    "amazon": "amazon.json",
    "microsoft": "microsoft.json",
    "nvidia": "nvidia.json",
    "novita": "novita.json",
    "moonshot": "moonshot.json",
    "xiaomi": "xiaomi.json",
    "sakana": "sakana.json",
}

DATA_DIR = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED_DIR = r"F:\Python314\Lib\site-packages\llmcapa\data"

print("Step 1: Fetching OpenRouter models...", flush=True)

# Fetch OpenRouter models
import llmcapa
count = llmcapa.fetch_openrouter(cache_ttl=0)
print(f"  Fetched {count} models from OpenRouter", flush=True)

# Get all models from registry
all_models = llmcapa.list_models()
print(f"  Total models in registry: {len(all_models)}", flush=True)

# Group by provider
by_provider = defaultdict(list)
for m in all_models:
    by_provider[m.provider].append(m)

print(f"  Providers in registry: {sorted(by_provider.keys())}", flush=True)

# Load existing bundled data to preserve non-OpenRouter models
existing_data = {}
for fname in os.listdir(DATA_DIR):
    if fname.endswith(".json") and fname not in ("ollama.json", "huggingface.json"):
        try:
            with open(os.path.join(DATA_DIR, fname), encoding="utf-8") as f:
                existing_data[fname] = json.load(f)
        except:
            pass

# Update or create JSON files for each provider
updated_providers = {}
for or_provider, bundled_name in PROVIDER_MAP.items():
    models_from_or = by_provider.get(or_provider, [])
    if not models_from_or:
        print(f"  {or_provider}: no models from OpenRouter, skipping", flush=True)
        continue
    
    # Convert Capability to dict
    entries = []
    for cap in models_from_or:
        d = cap.to_dict()
        # Ensure bundled JSON format
        if "extra" in d:
            del d["extra"]
        entries.append(d)
    
    entries.sort(key=lambda x: x["model_id"])
    
    # Merge with existing data (keep deprecated models not in OpenRouter)
    fname = PROVIDER_FILES.get(bundled_name)
    if fname and fname in existing_data:
        existing = existing_data[fname].get("models", [])
        existing_ids = {e["model_id"] for e in entries}
        for e in existing:
            if e.get("model_id") not in existing_ids and e.get("deprecated"):
                entries.append(e)
        entries.sort(key=lambda x: x["model_id"])
    
    # Write JSON
    if fname:
        filepath = os.path.join(DATA_DIR, fname)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump({"models": entries}, f, ensure_ascii=False, indent=2)
        updated_providers[bundled_name] = len(entries)
        print(f"  {bundled_name}/{fname}: {len(entries)} models written", flush=True)

# Also update openrouter.json (OpenRouter-specific models)
or_entries = []
for m in by_provider.get("openrouter", []):
    d = m.to_dict()
    if "extra" in d:
        del d["extra"]
    or_entries.append(d)
or_entries.sort(key=lambda x: x["model_id"])
or_path = os.path.join(DATA_DIR, "openrouter.json")
with open(or_path, "w", encoding="utf-8") as f:
    json.dump({"models": or_entries}, f, ensure_ascii=False, indent=2)
updated_providers["openrouter"] = len(or_entries)
print(f"  openrouter.json: {len(or_entries)} models written", flush=True)

# Copy all updated files to installed package
for fname in os.listdir(DATA_DIR):
    if fname.endswith(".json"):
        shutil.copy2(
            os.path.join(DATA_DIR, fname),
            os.path.join(INSTALLED_DIR, fname)
        )
print("  All JSON files copied to installed package", flush=True)

# Update provider_update_log.md
today = date.today().strftime("%Y-%m-%d")
log_path = r"F:\KAIHATSU\llmcapa\provider_update_log.md"
log_entry = f"""
## Bulk Update via OpenRouter API ({today})

### Source
- OpenRouter API: https://openrouter.ai/api/v1/models
- Method: fetch_openrouter(cache_ttl=0) via llmcapa

### Models Updated
"""
for prov, count in sorted(updated_providers.items()):
    log_entry += f"- {prov}: {count} models\n"

log_entry += "\n### Notes\n"
log_entry += "- All provider data refreshed from OpenRouter API (accurate pricing, context windows, capabilities)\n"
log_entry += "- Provider parameter is now required for search() to avoid cross-provider ambiguity\n"
log_entry += "- Ollama data (1,638 models) preserved as local-only (not available via OpenRouter)\n"
log_entry += "- Japanese domestic providers (NTT, ELYZA, SoftBank, NEC, Fujitsu, PFN) preserved from previous bundled data\n"
log_entry += "- LMStudio catalog preserved from previous bundled data\n"

with open(log_path, "a", encoding="utf-8") as f:
    f.write(log_entry)

print(f"\nDone! {len(updated_providers)} providers updated.", flush=True)
print(f"Log appended to provider_update_log.md", flush=True)
