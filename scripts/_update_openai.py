"""Update openai.json with scraped data and update provider_update_log.md."""
import json, re
from datetime import date

# ── Parsed OpenAI model data from scraped pages ──

FLAGSHIP_MODELS = {
    "gpt-5.6-sol": {
        "model_id": "gpt-5.6-sol",
        "display_name": "GPT-5.6 Sol",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": ["gpt-5.6"],
    },
    "gpt-5.6-terra": {
        "model_id": "gpt-5.6-terra",
        "display_name": "GPT-5.6 Terra",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 15.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": [],
    },
    "gpt-5.6-luna": {
        "model_id": "gpt-5.6-luna",
        "display_name": "GPT-5.6 Luna",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 1.0, "output_per_1m": 6.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2026-02-16",
        "aliases": [],
    },
    "gpt-5.5": {
        "model_id": "gpt-5.5",
        "display_name": "GPT-5.5",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-10-01",
        "aliases": [],
    },
    "gpt-5.5-pro": {
        "model_id": "gpt-5.5-pro",
        "display_name": "GPT-5.5 Pro",
        "context_window": 1048576,
        "max_output_tokens": 131072,
        "pricing": {"input_per_1m": 30.0, "output_per_1m": 180.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-10-01",
        "aliases": [],
    },
    "gpt-5.4": {
        "model_id": "gpt-5.4",
        "display_name": "GPT-5.4",
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 15.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-mini": {
        "model_id": "gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "context_window": 524288,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 0.75, "output_per_1m": 4.5, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-nano": {
        "model_id": "gpt-5.4-nano",
        "display_name": "GPT-5.4 Nano",
        "context_window": 262144,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 0.2, "output_per_1m": 1.25, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
    "gpt-5.4-pro": {
        "model_id": "gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "context_window": 1048576,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 30.0, "output_per_1m": 180.0, "currency": "USD"},
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_vision": True,
        "supports_responses_api": True,
        "supports_chat_completion": True,
        "knowledge_cutoff": "2025-07-01",
        "aliases": [],
    },
}

SPECIALIZED_MODELS = {
    "gpt-image-2": {
        "model_id": "gpt-image-2",
        "display_name": "GPT Image 2",
        "context_window": 131072,
        "max_output_tokens": 32768,
        "pricing": {"input_per_1m": 5.0, "output_per_1m": 30.0, "currency": "USD"},
        "input_modalities": ["text", "image"],
        "output_modalities": ["text", "image"],
        "supports_vision": True,
        "supports_function_calling": False,
        "supports_json_mode": True,
        "supports_streaming": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
    },
    "gpt-realtime-2.1": {
        "model_id": "gpt-realtime-2.1",
        "display_name": "GPT-Realtime 2.1",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 4.0, "output_per_1m": 24.0, "currency": "USD"},
        "input_modalities": ["text", "image", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning": True,
    },
    "gpt-realtime-2.1-mini": {
        "model_id": "gpt-realtime-2.1-mini",
        "display_name": "GPT-Realtime 2.1 Mini",
        "context_window": 131072,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 0.6, "output_per_1m": 2.4, "currency": "USD"},
        "input_modalities": ["text", "image", "audio"],
        "output_modalities": ["text", "audio"],
        "supports_vision": True,
        "supports_function_calling": True,
        "supports_chat_completion": False,
        "supports_responses_api": False,
        "supports_reasoning": True,
    },
    "gpt-4o-transcribe": {
        "model_id": "gpt-4o-transcribe",
        "display_name": "GPT-4o Transcribe",
        "context_window": 32768,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
    },
    "gpt-4o-mini-transcribe": {
        "model_id": "gpt-4o-mini-transcribe",
        "display_name": "GPT-4o Mini Transcribe",
        "context_window": 32768,
        "max_output_tokens": 16384,
        "pricing": {"input_per_1m": 1.25, "output_per_1m": 5.0, "currency": "USD"},
        "input_modalities": ["text", "audio"],
        "output_modalities": ["text"],
        "supports_chat_completion": False,
        "supports_streaming": True,
    },
    "gpt-5.3-codex": {
        "model_id": "gpt-5.3-codex",
        "display_name": "GPT-5.3 Codex",
        "context_window": 131072,
        "max_output_tokens": 65536,
        "pricing": {"input_per_1m": 1.75, "output_per_1m": 14.0, "currency": "USD"},
        "supports_function_calling": True,
        "supports_chat_completion": True,
        "supports_responses_api": True,
    },
    "sora-2": {
        "model_id": "sora-2",
        "display_name": "Sora 2",
        "context_window": 0,
        "max_output_tokens": 0,
        "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0, "currency": "USD"},
        "output_modalities": ["video"],
        "supports_chat_completion": False,
        "supports_streaming": False,
    },
}

# ── Read current openai.json ──
path = r"F:\KAIHATSU\llmcapa\src\llmcapa\data\openai.json"
with open(path, encoding="utf-8") as f:
    current = json.load(f)

# ── Build updated model list ──
updated = []
seen_ids = set()

# 1. Add flagship models
for mid, spec in FLAGSHIP_MODELS.items():
    entry = {"provider": "openai", "aliases": [], "deprecated": False, "input_modalities": ["text", "image"], "output_modalities": ["text"]}
    entry.update(spec)
    updated.append(entry)
    seen_ids.add(mid)

# 2. Add specialized models
for mid, spec in SPECIALIZED_MODELS.items():
    entry = {"provider": "openai", "aliases": [], "deprecated": False, "input_modalities": ["text"], "output_modalities": ["text"]}
    entry.update(spec)
    updated.append(entry)
    seen_ids.add(mid)

# 3. Preserve deprecated models from current data
for m in current.get("models", []):
    mid = m.get("model_id")
    if mid and mid not in seen_ids and m.get("deprecated"):
        updated.append(m)
        seen_ids.add(mid)

updated.sort(key=lambda x: x["model_id"])

# ── Write openai.json ──
output = {"models": updated}
with open(path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"openai.json: {len(updated)} models (flagship={len(FLAGSHIP_MODELS)}, specialized={len(SPECIALIZED_MODELS)}, deprecated preserved)", flush=True)

# ── Copy to installed package ──
import shutil
shutil.copy2(path, r"F:\Python314\Lib\site-packages\llmcapa\data\openai.json")
print("Installed package updated", flush=True)

# ── Update provider_update_log.md ──
log_path = r"F:\KAIHATSU\llmcapa\provider_update_log.md"
today = date.today().strftime("%Y-%m-%d")
log_entry = f"""
## OpenAI ({today})

### Source
- Official OpenAI API Documentation: https://developers.openai.com/api/docs/models
- Pricing page: https://developers.openai.com/api/docs/pricing
- Method: Playwright (headless browser) for JavaScript-rendered pages

### Models Updated
{len(updated)} models total

### Changes
- Added GPT-5.6 Sol/Terra/Luna (flagship models, context=1.05M, max_output=128K, reasoning effort supported)
- Added GPT-5.5, GPT-5.5 Pro
- Added GPT-5.4, GPT-5.4 Mini, GPT-5.4 Nano, GPT-5.4 Pro
- Added GPT Image 2, GPT-Realtime 2.1/Mini, GPT-4o Transcribe/Mini Transcribe
- Added GPT-5.3 Codex, Sora 2
- Removed: gpt-4o, gpt-4o-mini, gpt-4.1 series (deprecated by OpenAI)
- Pricing updated to latest (2026-07)
"""

with open(log_path, "a", encoding="utf-8") as f:
    f.write(log_entry)
print("provider_update_log.md updated", flush=True)

print("Done", flush=True)
