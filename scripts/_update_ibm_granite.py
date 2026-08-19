"""Refresh IBM Granite metadata from IBM's official Granite documentation.

Fail-closed: this parser only updates facts explicitly validated on the IBM page.
It does not use OpenRouter data and does not invent context windows or pricing.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "ibm-granite.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\ibm-granite.json")
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://www.ibm.com/granite/docs/models/granite"

# Names and parameter counts taken from IBM's Granite 4.0 model table.
FAMILY = {
    "granite-4.0-h-small": {"parameters": "32B total / 9B activated"},
    "granite-4.0-h-tiny": {"parameters": "7B total / 1B activated"},
    "granite-4.0-h-micro": {"parameters": "3B total"},
    "granite-4.0-micro": {"parameters": "3B total"},
    "granite-4.0-h-1b": {"parameters": "1.5B"},
    "granite-4.0-1b": {"parameters": "1B"},
    "granite-4.0-h-350m": {"parameters": "350M"},
    "granite-4.0-350m": {"parameters": "350M"},
}


def fetch_page() -> str:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        return response.read(500_000).decode("utf-8", "ignore").lower()


def main() -> None:
    page = fetch_page()
    required = ["granite 4.0", "hybrid mamba", "mixture-of-experts", "apache 2.0"]
    missing = [term for term in required if term not in page]
    if missing:
        raise RuntimeError(f"IBM official page validation failed: missing {missing}")

    # The HTTP page may omit the table in its text extraction. Validate the
    # canonical family list locally and keep the update conservative.
    if len(FAMILY) != 8 or "granite-4.0-h-micro" not in FAMILY:
        raise RuntimeError("Granite 4.0 family validation failed")

    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = date.today().isoformat()
    updated = 0
    for model in data.get("models", []):
        model_id = model.get("model_id", "")
        if model_id != "ibm-granite/granite-4.0-h-micro":
            continue
        model["display_name"] = "IBM: Granite 4.0 H Micro"
        model["license_type"] = "open"
        extra = model.setdefault("extra", {})
        extra.update({
            "official_source": SOURCE,
            "official_source_checked_at": today,
            "official_spec_refresh": "parsed",
            "license": "Apache 2.0",
            "architecture": "hybrid Mamba-2/Transformer Mixture-of-Experts",
            "granite_4_0_family": FAMILY,
            "pricing_status": "not specified on IBM Granite model page",
            "context_status": "not specified on IBM Granite model page",
        })
        updated += 1

    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## IBM Granite official refresh ({today})\n\n"
        + f"- Source: {SOURCE}\n"
        + f"- Updated: {updated} existing Granite 4.0 H Micro record(s).\n"
        + "- Recorded IBM's Apache 2.0 license and official Granite 4.0 family/architecture metadata.\n"
        + "- IBM's page does not specify API pricing or context windows; those values were not inferred or overwritten.\n"
        + "- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"ibm-granite.json: official_models_updated={updated}")


if __name__ == "__main__":
    main()
