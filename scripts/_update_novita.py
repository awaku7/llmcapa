"""Update novita.json with official pricing from Novita website (Playwright)."""
import json, os, re

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# Novita official pricing (scraped from https://novita.ai/pricing)
# Format: (model_id_substring, input_price, output_price)
NOVITA_PRICES = {
    "deepseek-v4-pro": (1.6, 3.2),
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v3.2": (0.269, 0.4),
    "deepseek-r1-0528": (0.7, 2.5),
    "deepseek-v3": (0.27, 1.12),
    "deepseek-r1": (0.7, 2.5),
    "qwen3.7-max": (1.25, 3.75),
    "qwen3.6-27b": (0.6, 3.6),
    "qwen3.5-27b": (0.3, 2.4),
    "qwen3.5-122b": (0.4, 3.2),
    "qwen3.5-35b": (0.25, 2.0),
    "qwen3.5-397b": (0.6, 3.6),
    "qwen3-coder-next": (0.2, 1.5),
    "qwen3-vl-235b": (0.98, 3.95),
    "qwen3-next-80b": (0.15, 1.5),
    "qwen3-coder-480b": (0.38, 1.55),
    "qwen3-coder-30b": (0.07, 0.27),
    "qwen3-235b": (0.09, 0.58),
    "qwen2.5-72b": (0.38, 0.4),
    "glm-5.2": (1.4, 4.4),
    "glm-5.1": (1.38, 4.4),
    "glm-5": (1.0, 3.2),
    "glm-4.7-flash": (0.07, 0.4),
    "glm-4.7": (0.6, 2.2),
    "glm-4.6": (0.55, 2.2),
    "kimi-k2.7": (0.95, 4.0),
    "kimi-k2.6": (0.8, 3.4),
    "kimi-k2.5": (0.6, 3.0),
    "minimax-m3": (0.3, 1.2),
    "minimax-m2.7": (0.3, 1.2),
    "minimax-m2.5": (0.3, 1.2),
    "gemma-4-26b": (0.13, 0.4),
    "gemma-4-31b": (0.14, 0.4),
    "llama-3.1-8b": (0.02, 0.05),
    "llama-3.3-70b": (0.135, 0.4),
    "llama-4-maverick": (0.27, 0.85),
    "llama-4-scout": (0.18, 0.59),
    "mistral-nemo": (0.04, 0.17),
    "mimo-v2.5": (0.168, 0.336),
    "mimo-v2.5-pro": (0.522, 1.044),
}

# Load novita.json
path = os.path.join(DATA, "novita.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

updated = 0
for m in data["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in NOVITA_PRICES.items():
        if key in mid:
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            updated += 1
            break

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Copy to installed
import shutil
shutil.copy2(path, os.path.join(INSTALLED, "novita.json"))

print(f"novita.json: {updated} models updated with official pricing", flush=True)
