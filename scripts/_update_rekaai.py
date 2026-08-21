"""Refresh Reka model availability from Reka's official model documentation."""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "rekaai.json"
INSTALLED = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "rekaai.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.reka.ai/chat/models"
PUBLIC = ["reka-flash", "reka-edge-2603"]


def main() -> None:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        text = response.read(500_000).decode("utf-8", "ignore").lower()
    if "reka-flash" not in text or "reka-edge-2603" not in text or "models" not in text:
        raise RuntimeError("Reka official models page validation failed")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    updated = 0
    for model in data.get("models", []):
        extra = model.setdefault("extra", {})
        extra.update({"official_source": SOURCE, "official_source_checked_at": today, "official_spec_refresh": "parsed", "official_public_models": PUBLIC, "models_api": "https://api.reka.ai/v1/models"})
        if model.get("model_id") == "rekaai/reka-edge":
            model["aliases"] = sorted(set(model.get("aliases", []) + ["reka-edge-2603"]))
        updated += 1
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(LOG.read_text(encoding="utf-8") + f"\n## Reka AI official refresh ({today})\n\n- Source: {SOURCE}\n- Parsed official public baseline models: reka-flash and reka-edge-2603.\n- Updated provenance/availability metadata for {updated} existing Reka records; numeric pricing/context values were not inferred.\n- OpenRouter was not used.\n", encoding="utf-8")
    print(f"rekaai.json: official_models_updated={updated}")

if __name__ == "__main__": main()
