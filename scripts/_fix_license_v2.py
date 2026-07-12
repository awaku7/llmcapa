"""Fix license_type: use 'in' matching for open-weight model names."""
import json, os, shutil

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

OPEN_KW = [
    "gemma", "llama", "phi", "mistral", "qwen", "nemotron", "granite",
    "starcoder", "falcon", "aya", "olmo", "dolphin", "yi", "zephyr",
    "vicuna", "wizard", "solar", "stable", "command", "nous", "hermes",
    "tulu", "deepseek", "glm", "minicpm", "internlm", "exaone", "grok",
    "kimi", "moonshot", "minimax", "gpt-oss", "sakana", "fugu",
    "tsuzumi", "elyza", "cotomi", "takane", "plamo", "sarashina",
    "cc-gov", "rnj", "ornith", "alfred", "laguna", "magicoder",
    "sqlcoder", "codebooga", "codegeex", "codeup", "opencoder",
    "north-mini", "reader-lm", "nuextract", "paraphrase",
    "mxbai", "bge", "nomic", "snowflake", "jina", "sora",
    "codellama", "codegemma", "stability", "cohere", "functiongemma",
]

for fname in os.listdir(DATA):
    if not fname.endswith(".json"):
        continue
    fpath = os.path.join(DATA, fname)
    with open(fpath, encoding="utf-8") as f:
        data = json.load(f)
    
    for m in data.get("models", []):
        pricing = m.get("pricing")
        if pricing is not None and isinstance(pricing, dict):
            inp = pricing.get("input_per_1m", -1)
            out = pricing.get("output_per_1m", -1)
            if inp == 0.0 and out == 0.0:
                m["license_type"] = "free"
            elif inp > 0 or out > 0:
                m["license_type"] = "api"
            continue
        
        if pricing is None:
            mid = m["model_id"].lower()
            if any(kw in mid for kw in OPEN_KW):
                m["license_type"] = "free"
            elif m.get("license_type") in (None, "unknown"):
                m["license_type"] = "license"
    
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

for fname in os.listdir(DATA):
    if fname.endswith(".json"):
        shutil.copy2(os.path.join(DATA, fname), os.path.join(INSTALLED, fname))
print("Done", flush=True)
