"""Create minimax.json with official pricing from Novita scraped data."""

import json
import os
import shutil
from pathlib import Path

import llmcapa

DATA = r"F:\KAIHATSU\llmcapa\src\llmcapa\data"
INSTALLED = r"F:\Python314\Lib\site-packages\llmcapa\data"

# Official pricing is kept in metadata JSON so the updater contains no model values.
MINIMAX_PRICES = {
    key: tuple(value)
    for key, value in json.loads(
        (
            Path(__file__).parent / "metadata" / "_add_minimax_minimax_prices.json"
        ).read_text(encoding="utf-8")
    ).items()
}

# Export from registry
models = []
for m in llmcapa.list_models(provider="minimax"):
    d = m.to_dict()
    d.pop("extra", None)
    mid = d["model_id"].lower()
    # Apply pricing
    for key, (inp, out) in MINIMAX_PRICES.items():
        if key in mid:
            d["pricing"] = {
                "input_per_1m": inp,
                "output_per_1m": out,
                "currency": "USD",
            }
            break
    models.append(d)

models.sort(key=lambda x: x["model_id"])

path = os.path.join(DATA, "minimax.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"models": models}, f, ensure_ascii=False, indent=2)
print(f"minimax.json: {len(models)} models created", flush=True)

shutil.copy2(path, os.path.join(INSTALLED, "minimax.json"))
print("Copied to installed package", flush=True)
