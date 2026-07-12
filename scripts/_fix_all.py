"""Fix pricing, FIM, Responses API flags, and merge duplicate providers."""
import json, os, shutil

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# ── 1. Anthropic official pricing ──
ANTHROPIC_PRICING = {
    "claude-fable-5": (10.0, 50.0, 1048576, 131072),
    "claude-opus-4-8": (5.0, 25.0, 1048576, 131072),
    "claude-opus-4-7": (5.0, 25.0, 1048576, 131072),
    "claude-opus-4-6": (5.0, 25.0, 1048576, 131072),
    "claude-opus-4-5": (5.0, 25.0, 1048576, 131072),
    "claude-sonnet-5": (3.0, 15.0, 1048576, 131072),
    "claude-sonnet-4-6": (3.0, 15.0, 1048576, 131072),
    "claude-sonnet-4-5": (3.0, 15.0, 1048576, 131072),
    "claude-haiku-4-5": (1.0, 5.0, 200000, 65536),
    "claude-haiku-3-5": (0.8, 4.0, 200000, 65536),
}

# ── 2. DeepSeek official pricing ──
DEEPSEEK_PRICING = {
    "deepseek-v4-flash": (0.14, 0.28, 1048576, 393216),
    "deepseek-v4-pro": (0.435, 0.87, 1048576, 393216),
}

# ── 3. FIM-capable model patterns ──
FIM_PATTERNS = [
    "codegemma", "codellama", "starcoder", "deepseek-coder", "deepseek-v4",
    "qwen2.5-coder", "qwen3-coder", "codeqwen", "stable-code", "wizardcoder",
    "magicoder", "phind-codellama", "codebooga", "codegeex4", "codeup",
    "sqlcoder", "opencoder", "yi-coder", "north-mini-code", "granite-code",
    "codestral", "devstral",
]

# ── 4. Responses API: only OpenAI/Azure ──
RESPONSES_PROVIDERS = {"openai", "azure-openai"}

# ── 5. Provider merge map ──
MERGE_MAP = {
    "meta-llama": "meta",
    "mistralai": "mistral",
    "mistral-ai": "mistral",
    "x-ai": "xai",
    "qwen-(alibaba)": "qwen",
}

def load_json(name):
    with open(os.path.join(DATA, name), encoding="utf-8") as f:
        return json.load(f)

def save_json(name, data):
    path = os.path.join(DATA, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_fim_model(model_id):
    mid = model_id.lower()
    for pat in FIM_PATTERNS:
        if pat in mid:
            return True
    return False

# ── Process all JSON files ──
for fname in os.listdir(DATA):
    if not fname.endswith(".json") or fname == "ollama.json":
        continue
    
    data = load_json(fname)
    prov = data.get("models", [{}])[0].get("provider", "") if data.get("models") else ""
    
    changed = 0
    for m in data.get("models", []):
        mid = m["model_id"]
        
        # Anthropic pricing
        if prov == "anthropic" and mid in ANTHROPIC_PRICING:
            inp, out, ctx, mxo = ANTHROPIC_PRICING[mid]
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            m["context_window"] = ctx
            m["max_output_tokens"] = mxo
            m["supports_thinking_budget"] = True
            m["supports_reasoning"] = True
            changed += 1
        
        # DeepSeek pricing
        if prov == "deepseek" and mid in DEEPSEEK_PRICING:
            inp, out, ctx, mxo = DEEPSEEK_PRICING[mid]
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            m["context_window"] = ctx
            m["max_output_tokens"] = mxo
            changed += 1
        
        # FIM flag (ollama already has it)
        if prov != "ollama":
            m["supports_fim"] = is_fim_model(mid)
        
        # Responses API: only OpenAI/Azure
        if prov not in RESPONSES_PROVIDERS:
            m["supports_responses_api"] = False
        
        # Google: supports_google_api=True
        if prov == "google":
            m["supports_google_api"] = True
            m["supports_chat_completion"] = True
        
        # Anthropic: supports_anthropic_api=True
        if prov == "anthropic":
            m["supports_anthropic_api"] = True
    
    if changed:
        print(f"  {fname}: {changed} models updated", flush=True)
    
    save_json(fname, data)

# ── Merge duplicate providers ──
for src_prov, dst_prov in MERGE_MAP.items():
    # Find source JSON file
    src_file = None
    for fname in os.listdir(DATA):
        if not fname.endswith(".json"):
            continue
        data = load_json(fname)
        models = data.get("models", [])
        if models and models[0].get("provider", "") == src_prov:
            src_file = fname
            break
    
    if not src_file:
        print(f"  No JSON for {src_prov}, checking registry...", flush=True)
        continue
    
    # Find destination JSON file
    dst_file = None
    for fname in os.listdir(DATA):
        if not fname.endswith(".json"):
            continue
        data = load_json(fname)
        models = data.get("models", [])
        if models and models[0].get("provider", "") == dst_prov:
            dst_file = fname
            break
    
    if not dst_file:
        print(f"  No JSON for {dst_prov}, skipping merge", flush=True)
        continue
    
    src_data = load_json(src_file)
    dst_data = load_json(dst_file)
    
    src_models = src_data.get("models", [])
    dst_models = dst_data.get("models", [])
    
    # Get existing IDs in destination
    dst_ids = {m["model_id"] for m in dst_models}
    
    # Add source models not in destination, with provider renamed
    added = 0
    for m in src_models:
        if m["model_id"] not in dst_ids:
            m["provider"] = dst_prov
            dst_models.append(m)
            added += 1
    
    if added:
        dst_models.sort(key=lambda x: x["model_id"])
        dst_data["models"] = dst_models
        save_json(dst_file, dst_data)
        print(f"  Merged {src_prov} -> {dst_prov}: {added} models added", flush=True)
    
    # Remove source file (models are now in destination)
    os.remove(os.path.join(DATA, src_file))
    print(f"  Removed {src_file} (merged into {dst_file})", flush=True)

# ── Copy to installed package ──
for fname in os.listdir(DATA):
    if fname.endswith(".json"):
        shutil.copy2(os.path.join(DATA, fname), os.path.join(INSTALLED, fname))
print("  Copied to installed package", flush=True)

print("Done", flush=True)
