from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "together.json"
URL = "https://www.together.ai/pricing"


def _price(value: str) -> float | None:
    values = re.findall(r"\$([0-9]+(?:\.[0-9]+)?)", value)
    if not values:
        if value.strip() in {"0.00", "0"}:
            return 0.0
        return None
    return float(values[0])


def scrape() -> dict[str, tuple[float, float]]:
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        html = response.read()
    soup = BeautifulSoup(html, "html.parser")
    result: dict[str, tuple[float, float]] = {}
    for table in soup.select("table.pricing_table"):
        headers = [x.get_text(" ", strip=True).lower() for x in table.select("thead th")]
        if headers[:3] != ["model", "input", "output"]:
            continue
        for row in table.select("tbody tr"):
            cells = [x.get_text(" ", strip=True) for x in row.find_all(["th", "td"])]
            if len(cells) < 3:
                continue
            input_price = _price(cells[1])
            output_price = _price(cells[2])
            if input_price is not None and output_price is not None:
                result.setdefault(cells[0], (input_price, output_price))
    return result


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def main() -> None:
    scraped = scrape()
    aliases = {
        "deepseekv4pro": "DeepSeek V4 Pro",
        "gemma431b": "Gemma 4 31B",
        "nvidianemotron3ultra550ba55b": "NVIDIA Nemotron 3 Ultra",
        "llama3370binstructturbo": "Llama 3.3 70B",
        "gptoss120b": "gpt-oss-120B",
        "gptoss20b": "gpt-oss-20B",
    }
    by_key = {_key(name): prices for name, prices in scraped.items()}
    data = json.loads(DATA.read_text(encoding="utf-8"))
    changed = 0
    matched: list[str] = []
    for model in data["models"]:
        name_key = _key(model.get("display_name", ""))
        source_name = aliases.get(name_key, model.get("display_name", ""))
        prices = by_key.get(_key(source_name))
        if prices is None:
            continue
        model["pricing"] = {
            "input_per_1m": prices[0],
            "output_per_1m": prices[1],
            "currency": "USD",
        }
        model.setdefault("extra", {})["source"] = URL
        model["extra"]["pricing_retrieved_at"] = datetime.now(timezone.utc).isoformat()
        changed += 1
        matched.append(model["model_id"])
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"scraped_models": len(scraped), "updated_entries": changed, "matched": matched}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
