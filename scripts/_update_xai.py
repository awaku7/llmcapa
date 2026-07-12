"""Update xai.json with official Grok pricing from docs.x.ai."""
import json, shutil

path = r"F:\KAIHATSU\llmcapa\src\llmcapa\data\xai.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

# xAI official pricing (from docs.x.ai)
XAI_PRICES = {
    "grok-4.5": (2.0, 6.0, 500000),
    "grok-4.3": (1.5, 5.0, 500000),
    "grok-4.20": (3.0, 15.0, 2000000),
    "grok-4.1": (0.5, 2.0, 131072),
    "grok-4": (0.5, 2.0, 131072),
    "grok-3": (0.3, 1.5, 131072),
    "grok-2": (0.2, 1.0, 65536),
    "grok-1": (0.1, 0.5, 8192),
    "grok-build": (2.0, 8.0, 1000000),
}

for m in data["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out, ctx) in XAI_PRICES.items():
        if key in mid:
            m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            m["context_window"] = ctx
            m["supports_reasoning"] = True
            m["supports_function_calling"] = True
            break

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

shutil.copy2(path, r"F:\Python314\Lib\site-packages\llmcapa\data\xai.json")
print(f"xai.json: updated with official xAI pricing", flush=True)
