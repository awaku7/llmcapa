"""Create minimax.json with official pricing from Novita scraped data."""
import json, os, shutil
import llmcapa

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# MiniMax official pricing (from Novita pricing page & known info)
MINIMAX_PRICES = {
    "minimax-m1": (0.55, 2.2),
    "minimax-m2": (0.3, 1.2),
    "minimax-m2.1": (0.3, 1.2),
    "minimax-m2.5": (0.3, 1.2),
    "minimax-m2.7": (0.3, 1.2),
    "minimax-m3": (0.3, 1.2),
    "minimax-01": (0.2, 1.1),
}

# Export from registry
models = []
for m in llmcapa.list_models(provider='minimax'):
    d = m.to_dict()
    d.pop("extra", None)
    mid = d["model_id"].lower()
    # Apply pricing
    for key, (inp, out) in MINIMAX_PRICES.items():
        if key in mid:
            d["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
            break
    models.append(d)

models.sort(key=lambda x: x["model_id"])

path = os.path.join(DATA, "minimax.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"models": models}, f, ensure_ascii=False, indent=2)
print(f"minimax.json: {len(models)} models created", flush=True)

shutil.copy2(path, os.path.join(INSTALLED, "minimax.json"))
print("Copied to installed package", flush=True)
