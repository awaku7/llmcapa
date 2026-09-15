"""Update azure_foundry.json with official Azure pricing and add Cohere pricing."""

import json
import os
import shutil
from pathlib import Path

DATA = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")
INSTALLED = str(Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data")

# 1. Azure OpenAI official pricing (from azure.microsoft.com)
AZURE_PRICES = json.loads(
    (
        Path(__file__).parent / "metadata" / "_update_azure_cohere_azure_prices.json"
    ).read_text(encoding="utf-8")
)

# 2. Cohere official pricing (from cohere.com FAQ)
COHERE_PRICES = json.loads(
    (
        Path(__file__).parent / "metadata" / "_update_azure_cohere_cohere_prices.json"
    ).read_text(encoding="utf-8")
)

# Update azure_foundry.json
path_az = os.path.join(DATA, "azure_foundry.json")
with open(path_az, encoding="utf-8") as f:
    az = json.load(f)

az_count = 0
for m in az["models"]:
    mid = m["model_id"].lower()
    for key, (inp, out) in AZURE_PRICES.items():
        if key in mid:
            m["pricing"] = {
                "input_per_1m": inp,
                "output_per_1m": out,
                "currency": "USD",
            }
            m["supports_responses_api"] = True
            az_count += 1
            break

with open(path_az, "w", encoding="utf-8") as f:
    json.dump(az, f, ensure_ascii=False, indent=2)
print(
    f"azure_foundry.json: {az_count}/{len(az['models'])} models updated with Azure official pricing",
    flush=True,
)

# DATA and INSTALLED intentionally point at the same source tree in this
# checkout. Avoid copying a file onto itself (Windows raises WinError 32).
dst_az = os.path.abspath(os.path.join(INSTALLED, "azure_foundry.json"))
if os.path.abspath(path_az) != dst_az:
    shutil.copy2(path_az, dst_az)
    print("Copied to installed package", flush=True)
else:
    print("Installed path is the source path; copy skipped", flush=True)
print("Done", flush=True)
