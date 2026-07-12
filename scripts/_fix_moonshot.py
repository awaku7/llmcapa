"""Update moonshot.json with Kimi official pricing from Novita."""
import json, shutil

path = r"F:\KAIHATSU\llmcapa\src\llmcapa\data\moonshot.json"
with open(path, encoding="utf-8") as f:
    data = json.load(f)

prices = {
    "kimi-k2.7-code": (0.95, 4.0),
    "kimi-k2.6": (0.8, 3.4),
    "kimi-k2.5": (0.6, 3.0),
}

for m in data["models"]:
    mid = m["model_id"]
    if mid in prices:
        inp, out = prices[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

shutil.copy2(path, r"F:\Python314\Lib\site-packages\llmcapa\data\moonshot.json")
print(f"moonshot.json: updated {len(prices)} models", flush=True)
