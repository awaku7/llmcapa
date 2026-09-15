"""Update novita.json with official pricing from Novita website (Playwright)."""

import json
import os
from pathlib import Path

DATA = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")
INSTALLED = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")

# Novita official pricing (scraped from https://novita.ai/pricing)
# Format: (model_id_substring, input_price, output_price)
NOVITA_PRICES = json.loads(
    (
        Path(__file__).parent / "metadata" / "_update_novita_novita_prices.json"
    ).read_text(encoding="utf-8")
)

# Load novita.json
path = os.path.join(DATA, "novita.json")
with open(path, encoding="utf-8") as f:
    data = json.load(f)

updated = 0
for m in data["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in NOVITA_PRICES.items():
        if key in mid:
            m["pricing"] = {
                "input_per_1m": inp,
                "output_per_1m": out,
                "currency": "USD",
            }
            updated += 1
            break

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Copy to installed
import shutil

if os.path.abspath(path) != os.path.abspath(os.path.join(INSTALLED, "novita.json")):
    shutil.copy2(path, os.path.join(INSTALLED, "novita.json"))

print(f"novita.json: {updated} models updated with official pricing", flush=True)
