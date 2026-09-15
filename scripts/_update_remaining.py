"""Update remaining providers with officially scraped pricing data."""

import json
import os
import shutil
from pathlib import Path

DATA = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")
INSTALLED = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")

# Official pricing is kept in metadata JSON so the updater contains no model values.
MISTRAL_PRICES = {
    key: tuple(value)
    for key, value in json.loads(
        (
            Path(__file__).parent / "metadata" / "_update_remaining_mistral_prices.json"
        ).read_text(encoding="utf-8")
    ).items()
}

path_mistral = os.path.join(DATA, "mistral.json")
with open(path_mistral, encoding="utf-8") as f:
    mistral = json.load(f)

updated = 0
for m in mistral["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in MISTRAL_PRICES.items():
        if key in mid:
            m["pricing"] = {
                "input_per_1m": inp,
                "output_per_1m": out,
                "currency": "USD",
            }
            updated += 1
            break

with open(path_mistral, "w", encoding="utf-8") as f:
    json.dump(mistral, f, ensure_ascii=False, indent=2)
print(
    f"mistral.json: {updated}/{len(mistral['models'])} models updated with official pricing",
    flush=True,
)

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

# DATA and INSTALLED intentionally point at the same source tree in this
# checkout. Avoid copying files onto themselves (Windows raises WinError 32).
for source in (path_mistral, path_meta):
    destination = os.path.abspath(os.path.join(INSTALLED, os.path.basename(source)))
    if os.path.abspath(source) != destination:
        shutil.copy2(source, destination)
        print(f"Copied {os.path.basename(source)} to installed package", flush=True)
    else:
        print(
            f"Installed path for {os.path.basename(source)} is the source path; copy skipped",
            flush=True,
        )
print("Done", flush=True)
