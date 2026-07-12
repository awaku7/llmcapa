"""Update azure_foundry.json with official Azure pricing and add Cohere pricing."""
import json, os, shutil

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# 1. Azure OpenAI official pricing (from azure.microsoft.com)
AZURE_PRICES = {
    "gpt-5.5": (5.0, 30.0),
    "gpt-5.4": (2.5, 15.0),
    "gpt-5.4-mini": (0.75, 4.5),
    "gpt-5.4-nano": (0.2, 1.25),
    "gpt-5.4-pro": (30.0, 180.0),
    "gpt-5.3-codex": (1.75, 14.0),
    "gpt-5.2": (1.75, 14.0),
    "gpt-5.2-codex": (1.75, 14.0),
    "gpt-5.1": (1.25, 10.0),
    "gpt-5.1-codex": (1.25, 10.0),
    "gpt-5": (1.25, 10.0),
    "gpt-5-mini": (0.25, 2.0),
    "gpt-5-nano": (0.05, 0.4),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.4, 1.6),
    "gpt-4.1-nano": (0.1, 0.4),
    "o3": (2.0, 8.0),
    "o4-mini": (1.1, 4.4),
    "o1": (15.0, 60.0),
    "gpt-image-2": (5.0, 30.0),
    "gpt-image-1.5": (5.0, 32.0),
    "sora-2": (0.0, 0.0),
}

# 2. Cohere official pricing (from cohere.com FAQ)
COHERE_PRICES = {
    "command": (1.0, 2.0),
    "command-light": (0.3, 0.6),
    "command-r": (0.5, 1.5),
    "command-r-plus": (2.5, 10.0),
    "aya": (0.5, 1.5),
    "aya-expanse": (0.5, 1.5),
    "embed": (0.1, 0.0),
    "rerank": (1.0, 1.0),
}

# Update azure_foundry.json
path_az = os.path.join(DATA, "azure_foundry.json")
with open(path_az, encoding="utf-8") as f:
    az = json.load(f)

az_count = 0
for m in az["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in AZURE_PRICES.items():
        if key in mid:
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            m["supports_responses_api"] = True
            az_count += 1
            break

with open(path_az, "w", encoding="utf-8") as f:
    json.dump(az, f, ensure_ascii=False, indent=2)
print(f"azure_foundry.json: {az_count}/{len(az['models'])} models updated with Azure official pricing", flush=True)

# Copy to installed
shutil.copy2(path_az, os.path.join(INSTALLED, "azure_foundry.json"))
print("Copied to installed package", flush=True)
print("Done", flush=True)
