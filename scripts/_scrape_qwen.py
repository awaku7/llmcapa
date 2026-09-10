"""Fetch current Qwen International list prices from Alibaba Cloud docs."""
from __future__ import annotations

import html
import re
from urllib.request import Request, urlopen

PRICING_URL = "https://www.alibabacloud.com/help/en/model-studio/model-pricing"


def fetch_qwen_catalog() -> dict[str, dict]:
    request = Request(PRICING_URL, headers={"User-Agent": "llmcapa catalog updater"})
    with urlopen(request, timeout=30) as response:
        page = html.unescape(response.read().decode("utf-8", errors="replace"))

    result: dict[str, dict] = {}
    for raw_row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.I | re.S):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", raw_row, re.I | re.S)
        if len(cells) < 5:
            continue
        model_match = re.search(r"\bqwen[a-z0-9][a-z0-9._-]*", cells[0], re.I)
        if not model_match:
            continue
        model_id = model_match.group(0).lower()
        cell_text = [re.sub(r"<[^>]+>", " ", cell) for cell in cells]
        joined = " ".join(cell_text)
        raw_joined = " ".join(cells)
        # The first two dollar values are the first International pricing tier.
        prices = [float(value) for value in re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", joined)]
        if len(prices) < 2 or model_id in result:
            continue
        sizes = []
        for value, unit in re.findall(r"(?:≤|<)\s*([0-9]+(?:\.[0-9]+)?)\s*([KM])", raw_joined, re.I):
            sizes.append(float(value) * (1_000 if unit.upper() == "K" else 1_000_000))
        result[model_id] = {
            "input_per_1m": prices[0],
            "output_per_1m": prices[1],
            "context_window": int(max(sizes)) if sizes else 0,
            "source": PRICING_URL,
        }
    if not result:
        raise RuntimeError("no Qwen International prices found in official Alibaba docs")
    return result


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_qwen_catalog(), ensure_ascii=False, indent=2))
