"""Apply Playwright-scraped data to JSON files and update provider log."""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from _audio_capability_postprocess import apply as apply_audio_capabilities
from _image_capability_postprocess import apply as apply_image_capabilities
from _video_capability_postprocess import apply as apply_video_capabilities
from _structured_capability_postprocess import apply as apply_structured_capabilities

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

today = datetime.now(timezone.utc).date().strftime("%Y-%m-%d")

# ── 1. Update anthropic.json with official pricing ──
anthro_path = os.path.join(DATA, "anthropic.json")
with open(anthro_path, encoding="utf-8") as f:
    anthro = json.load(f)

ANTHRO_PRICES = json.loads(
    (Path(__file__).parent / "metadata" / "anthro_prices.json").read_text(
        encoding="utf-8"
    )
)

anthro_count = 0
for m in anthro["models"]:
    mid = m["model_id"]
    if mid in ANTHRO_PRICES:
        inp, out, ctx, mxo = ANTHRO_PRICES[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
        m["context_window"] = ctx
        m["max_output_tokens"] = mxo
        m["supports_thinking_budget"] = True
        m["supports_anthropic_api"] = True
        m["supports_responses_api"] = False
        anthro_count += 1

with open(anthro_path, "w", encoding="utf-8") as f:
    json.dump(anthro, f, ensure_ascii=False, indent=2)
print(
    f"anthropic.json: {anthro_count} models updated with official pricing", flush=True
)

# ── 2. Update deepseek.json with official pricing ──
ds_path = os.path.join(DATA, "deepseek.json")
with open(ds_path, encoding="utf-8") as f:
    ds = json.load(f)

DS_PRICES = json.loads(
    (Path(__file__).parent / "metadata" / "ds_prices.json").read_text(encoding="utf-8")
)

ds_count = 0
for m in ds["models"]:
    mid = m["model_id"]
    if mid in DS_PRICES:
        inp, out, ctx, mxo = DS_PRICES[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
        m["context_window"] = ctx
        m["max_output_tokens"] = mxo
        m["supports_fim"] = True
        ds_count += 1

with open(ds_path, "w", encoding="utf-8") as f:
    json.dump(ds, f, ensure_ascii=False, indent=2)
print(f"deepseek.json: {ds_count} models updated with official pricing", flush=True)

# ── 3. Fix FIM flags for all non-Ollama providers ──
FIM_PATTERNS = [
    "codegemma",
    "codellama",
    "starcoder",
    "deepseek-coder",
    "deepseek-v4",
    "qwen2.5-coder",
    "qwen3-coder",
    "codeqwen",
    "stable-code",
    "wizardcoder",
    "magicoder",
    "phind-codellama",
    "codebooga",
    "codegeex4",
    "codeup",
    "sqlcoder",
    "opencoder",
    "yi-coder",
    "north-mini-code",
    "granite-code",
    "codestral",
    "devstral",
]

fim_count = 0
for fname in os.listdir(DATA):
    if not fname.endswith(".json") or fname == "ollama.json":
        continue
    fpath = os.path.join(DATA, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("models", []):
        mid = m["model_id"].lower()
        is_fim = any(p in mid for p in FIM_PATTERNS)
        if m.get("supports_fim") != is_fim:
            m["supports_fim"] = is_fim
            fim_count += 1
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print(f"FIM flags fixed for {fim_count} models across all providers", flush=True)

# ── 4. Fix Responses API: only OpenAI/Azure ──
resp_count = 0
for fname in os.listdir(DATA):
    if not fname.endswith(".json") or fname == "ollama.json":
        continue
    fpath = os.path.join(DATA, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    models = data.get("models", [])
    if not models:
        continue
    prov = models[0].get("provider", "")
    if prov not in ("openai", "azure-openai"):
        for m in models:
            if m.get("supports_responses_api", False):
                m["supports_responses_api"] = False
                resp_count += 1
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

print(f"Responses API: {resp_count} models fixed (only OpenAI/Azure)", flush=True)

# ── 4.5. Normalize audio capability records ──
audio_changes = apply_audio_capabilities(Path(DATA))
print(f"AudioCapability records updated: {audio_changes}", flush=True)

# ── 4.6. Normalize video capability records ──
video_changes = apply_video_capabilities(Path(DATA))
print(f"VideoCapability records updated: {video_changes}", flush=True)

# ── 4.7. Normalize structured capability records ──
structured_changes = apply_structured_capabilities(Path(DATA))
print(f"Structured capabilities updated: {structured_changes}", flush=True)

# ── 4.8. Normalize image-generation capability records ──
image_changes = apply_image_capabilities(Path(DATA))
print(f"ImageCapability records added: {image_changes}", flush=True)
# ── 5. Fix provider names: meta-llama->meta, x-ai->xai ──
rename_map = {"meta-llama": "meta", "x-ai": "xai"}
for fname in ["meta.json", "xai.json"]:
    fpath = os.path.join(DATA, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    models = data.get("models", [])
    old_prov = models[0].get("provider", "") if models else ""
    if old_prov in rename_map:
        new_prov = rename_map[old_prov]
        for m in models:
            m["provider"] = new_prov
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"{fname}: provider {old_prov} -> {new_prov}", flush=True)

# ── 6. Copy all to installed package ──
for fname in os.listdir(DATA):
    if fname.endswith(".json"):
        shutil.copy2(os.path.join(DATA, fname), os.path.join(INSTALLED, fname))
print("All JSON files copied to installed package", flush=True)

# ── 7. Update provider_update_log.md ──
log_path = r"F:\KAIHATSU\llmcapa\provider_update_log.md"
log_entry = f"""
## Fixes Applied ({today})

### Source
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing (Playwright)
- DeepSeek: https://api-docs.deepseek.com/quick_start/pricing (Playwright)
- FIM flags: pattern-based for code completion models
- Responses API: restricted to OpenAI/Azure only
- Audio metadata: provider documentation plus conservative modality-derived fields
- Video metadata: provider documentation plus conservative modality-derived fields
- Structured capabilities: document, embedding, rerank, and spatial metadata

### Changes
- **Anthropic**: {anthro_count} models updated with official pricing (Fable 5 $10/$50, Opus 4.8 $5/$25, Sonnet 5 $3/$15, Haiku 4.5 $1/$5)
- **DeepSeek**: {ds_count} models updated with official pricing (v4-flash $0.14/$0.28, v4-pro $0.435/$0.87)
- **FIM flags**: {fim_count} models corrected (codegemma, codellama, starcoder2, deepseek-coder, qwen-coder, etc.)
- **Responses API**: {resp_count} non-OpenAI/Azure models set to False
- **AudioCapability**: {audio_changes.get('records_changed', 0)} audio records enriched
- **VideoCapability**: {video_changes.get('records_changed', 0)} video records enriched
- **Structured capabilities**: {structured_changes.get('records_changed', 0)} records enriched
- **Provider names**: meta-llama->meta, x-ai->xai (consolidated)
"""
with open(log_path, "a", encoding="utf-8") as f:
    f.write(log_entry)
print("provider_update_log.md updated", flush=True)

print("Done", flush=True)
