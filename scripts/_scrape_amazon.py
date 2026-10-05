"""Fetch current Amazon Nova prices from official AWS sources."""
from __future__ import annotations

import gzip
import html
import json
import re
from urllib.request import Request, urlopen

PRICING_URL = "https://aws.amazon.com/nova/pricing/"
METERED_URL = (
    "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/"
    "bedrock/USD/current/bedrock.json"
)
REGION = "US East (N. Virginia)"


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "llmcapa catalog updater"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def _model_id(title: str) -> str:
    name = re.sub(r"^Amazon\s+", "", title, flags=re.I)
    name = re.sub(r"\s*\(Preview\)\s*$", "", name, flags=re.I)
    name = re.sub(r"\s+", "-", name.strip().lower())
    return (name if name.startswith("nova-") else "nova-" + name) + "-v1"


def _plain(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", value)).strip()


def fetch_nova_prices() -> dict[str, dict[str, float]]:
    """Return current text input/output prices keyed by official model ID."""
    page = html.unescape(_fetch(PRICING_URL).decode("utf-8", errors="replace"))
    meter = json.loads(gzip.decompress(_fetch(METERED_URL)))
    region = meter["regions"][REGION]
    result: dict[str, dict[str, float]] = {}

    for table in re.findall(r"<table>(.*?)</table>", page, re.I | re.S):
        headers = [_plain(v).lower() for v in re.findall(r"<th[^>]*>(.*?)</th>", table, re.I | re.S)]
        if not headers:
            continue
        input_index = next(
            (i for i, h in enumerate(headers) if "input tokens (text)" in h),
            next((i for i, h in enumerate(headers) if "input tokens" in h), -1),
        )
        output_index = next(
            (i for i, h in enumerate(headers) if "output tokens (text)" in h),
            next((i for i, h in enumerate(headers) if "output tokens" in h), -1),
        )
        if input_index < 0 or output_index < 0:
            continue
        for row in re.findall(r"<tr>\s*<td>(.*?)</td>(.*?)</tr>", table, re.I | re.S):
            cells = [row[0]] + re.findall(r"<td>(.*?)</td>", row[1], re.I | re.S)
            if not cells or not _plain(cells[0]).lower().startswith("amazon nova"):
                continue
            if max(input_index, output_index) >= len(cells):
                continue

            def cell_price(cell: str) -> float | None:
                match = re.search(
                    r"priceOf!bedrock/bedrock!([^!]+)!\*!([0-9]+)", cell
                )
                if not match:
                    return None
                key, multiplier = match.groups()
                return float(region[key]["price"]) * int(multiplier)

            input_price = cell_price(cells[input_index])
            output_price = cell_price(cells[output_index])
            if input_price is None or output_price is None:
                continue
            model_id = _model_id(_plain(cells[0]))
            result.setdefault(model_id, {"input": input_price, "output": output_price})

    if not result:
        raise RuntimeError("no Amazon Nova prices found in official AWS pricing page")
    return result


if __name__ == "__main__":
    print(json.dumps(fetch_nova_prices(), ensure_ascii=False, indent=2))
