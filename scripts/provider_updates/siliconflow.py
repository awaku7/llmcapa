"""Update the siliconflow catalog from its official model page only."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/siliconflow.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.siliconflow.com/en/userguide/quickstart"
PATTERN = "(?<![\\w/])(?:Qwen|deepseek|THUDM|Pro|Kimi|moonshotai|zai-org|Wan-AI|black-forest-labs)[\\w./:-]+"


def fetch():
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-scraper/1.0"})
    try:
        with urlopen(req, timeout=60) as r:
            return r.read().decode("utf-8", "ignore")
    except Exception:  # noqa: BLE001
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            b = pw.chromium.launch(headless=True)
            p = b.new_page()
            p.goto(SOURCE, wait_until="networkidle", timeout=90000)
            text = p.locator("body").inner_text()
            b.close()
            return text


def update_catalog():
    text = fetch()
    ids = sorted(
        {
            re.sub(r"^accounts/[^/]+/models/", "", x.strip("`'\".,;:()[]"))
            for x in re.findall(PATTERN, text, re.IGNORECASE)
            if 2 < len(x) < 160 and not x.lower().endswith(("model", "models", "api"))
        },
        key=str.lower,
    )
    if not ids:
        raise RuntimeError("no model IDs found")
    rows = [
        {
            "provider": "siliconflow",
            "model_id": x,
            "display_name": x,
            "context_window": 0,
            "max_output_tokens": 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "supports_chat_completion": True,
            "supports_streaming": True,
            "supports_function_calling": None,
            "supports_json_mode": None,
            "supports_vision": None,
            "supports_reasoning": None,
            "supports_responses_api": False,
            "pricing": None,
            "deprecated": False,
            "aliases": [],
            "extra": {
                "source": SOURCE,
                "source_type": "official_page_scrape",
                "spec_status": "listed_only",
            },
        }
        for x in ids
    ]
    DATA.write_text(
        json.dumps({"models": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## siliconflow official refresh ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Updated: {len(rows)} model IDs.\n",
        encoding="utf-8",
    )
    print("siliconflow: updated", len(rows))


"""Update endpoint metadata for the siliconflow provider only."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/siliconflow.json"
LOG = ROOT / "provider_update_log.md"
BASE_URL = "https://api.siliconflow.cn/v1"
SOURCE = "https://docs.siliconflow.com/"


def update_endpoints():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    n = 0
    for model in data.get("models", []):
        model.setdefault("extra", {})["endpoints"] = [
            {
                "base_url": BASE_URL,
                "protocol": "openai-compatible",
                "auth": "bearer",
                "source": SOURCE,
            }
        ]
        n += 1
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## siliconflow endpoint metadata refresh ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Updated: {n} models.\n",
        encoding="utf-8",
    )
    print("siliconflow: endpoint metadata updated", n)


def main():
    update_catalog()
    update_endpoints()


if __name__ == "__main__":
    main()
