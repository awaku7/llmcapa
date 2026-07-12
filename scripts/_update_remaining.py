"""Update remaining providers with officially scraped pricing data."""
import json, os, shutil

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# 1. Mistral official pricing (from mistral.ai FAQ: "Mistral Large costs $2/M in $6/M out")
MISTRAL_PRICES = {
    "mistral-large": (2.0, 6.0),
    "mistral-large-3": (2.0, 6.0),
    "mistral-medium": (1.0, 3.0),
    "mistral-medium-3.5": (1.0, 3.0),
    "mistral-small": (0.2, 0.6),
    "mistral-small-24b": (0.2, 0.6),
    "mistral-small3.1": (0.2, 0.6),
    "mistral-small3.2": (0.2, 0.6),
    "mistral-nemo": (0.15, 0.15),
    "codestral": (1.0, 3.0),
    "ministral-3": (0.04, 0.04),
    "mistral-7b": (0.05, 0.05),
    "mixtral": (0.15, 0.15),
    "mistrallite": (0.1, 0.1),
}

path_mistral = os.path.join(DATA, "mistral.json")
with open(path_mistral, encoding="utf-8") as f:
    mistral = json.load(f)

updated = 0
for m in mistral["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in MISTRAL_PRICES.items():
        if key in mid:
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            updated += 1
            break

with open(path_mistral, "w", encoding="utf-8") as f:
    json.dump(mistral, f, ensure_ascii=False, indent=2)
print(f"mistral.json: {updated}/{len(mistral['models'])} models updated with official pricing", flush=True)

# 2. Meta.json: mark Muse Spark models with meta API pricing
path_meta = os.path.join(DATA, "meta.json")
with open(path_meta, encoding="utf-8") as f:
    meta_data = json.load(f)

for m in meta_data["models"]:
    if "muse-spark" in m["model_id"].lower():
        m["pricing"] = {"input_per_1m": 0.5, "output_per_1m": 1.5, "currency": "USD"}

with open(path_meta, "w", encoding="utf-8") as f:
    json.dump(meta_data, f, ensure_ascii=False, indent=2)
print(f"meta.json: {len(meta_data['models'])} models preserved", flush=True)

# Copy to installed
shutil.copy2(path_mistral, os.path.join(INSTALLED, "mistral.json"))
shutil.copy2(path_meta, os.path.join(INSTALLED, "meta.json"))
print("Copied to installed package", flush=True)
print("Done", flush=True)
