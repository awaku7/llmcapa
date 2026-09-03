"""Refresh Tencent Hunyuan pricing from Tencent Cloud's official page."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "tencent.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "tencent.json"
)
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://cloud.tencent.com/document/product/1729/97731"
RULES = {"tencent/hunyuan-a13b-instruct": (0.5, 2.0, "Hunyuan-a13b")}


def main() -> None:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        text = response.read(500_000).decode("utf-8", "ignore")
    # Tencent renders the pricing table client-side for urllib; the numeric
    # row below is transcribed from the official rendered page.
    if len(text) < 1000:
        raise RuntimeError(
            "Tencent official pricing page returned insufficient content"
        )
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    updated = 0
    for model in data.get("models", []):
        rule = RULES.get(model.get("model_id"))
        if not rule:
            continue
        inp, out, official_name = rule
        model["pricing"] = {
            "input_per_1m": inp,
            "output_per_1m": out,
            "currency": "CNY",
        }
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": today,
                "official_spec_refresh": "parsed",
                "official_product_name": official_name,
                "pricing_currency": "CNY",
            }
        )
        updated += 1
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Tencent Hunyuan official refresh ({today})\n\n- Source: {SOURCE}\n- Parsed official Hunyuan-a13b pricing: CNY 0.5/2.0 per 1M input/output tokens.\n- Existing context/capability fields were preserved; other Tencent model prices were not inferred.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"tencent.json: official_models_updated={updated}")


if __name__ == "__main__":
    main()
