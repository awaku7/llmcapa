"""Fetch MiniMax Pay-as-You-Go prices from the official MiniMax documentation.

MiniMax hosts its docs on Mintlify, so every guide is also served as raw
Markdown by appending ``.md`` to the URL. That keeps this scraper limited to
the standard library instead of driving a headless browser.

``fetch_minimax_catalog()`` returns ``{model_id: entry}``. Text models carry
``input``/``output`` (USD per 1M tokens); specialty models carry
``specialty_price`` (USD per unit). ``_update_minimax.py`` uses these values to
refresh the bundled catalog without hard-coding live prices.

Sources:
- https://platform.minimax.io/docs/guides/pricing-paygo
"""

from __future__ import annotations

import re
from urllib.request import Request, urlopen

PRICING_URL = "https://platform.minimax.io/docs/guides/pricing-paygo.md"

_HTML_TAG = re.compile(r"<[^>]+>")
_PRICE = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")
_MODEL_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9._-]*")
_SPEECH_MODEL = re.compile(r"\b(speech-[A-Za-z0-9._-]+)\b")


def _fetch(url: str) -> str:
    request = Request(url, headers={"User-Agent": "llmcapa catalog updater"})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def _strip(cell: str) -> str:
    text = _HTML_TAG.sub("", cell)
    return text.replace("\\$", "$").replace("**", "").replace("~~", "").strip()


def _last_price(cell: str) -> float | None:
    prices = _PRICE.findall(cell)
    return float(prices[-1]) if prices else None


def _first_model_id(cell: str) -> str | None:
    match = _MODEL_TOKEN.search(_strip(cell))
    return match.group(0) if match else None


def _split_row(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_alignment(cells: list[str]) -> bool:
    return bool(cells) and all(set(c) <= set(":- ") for c in cells if c)


def _table_rows(markdown: str):
    # Mintlify splits long cells across physical lines; reassemble each logical
    # row by buffering until a line ends with the closing "|".
    buffer = None
    for raw in markdown.splitlines():
        line = raw.strip()
        if buffer is None:
            if line.startswith("|"):
                buffer = line
        else:
            buffer = f"{buffer} {line}"
        if buffer is not None and buffer.endswith("|"):
            cells = _split_row(buffer)
            buffer = None
            if _is_alignment(cells):
                continue
            yield cells


def _store_specialty(result: dict[str, dict], model_id: str, price: float) -> None:
    entry = result.setdefault(model_id, {})
    entry.setdefault("specialty_price", price)
    lowered = model_id.lower()
    if lowered != model_id:
        result.setdefault(lowered, entry)


def _collect_text(cells: list[str], result: dict[str, dict]) -> None:
    if len(cells) < 3 or "M tokens" not in cells[1] or "M tokens" not in cells[2]:
        return
    model_id = _first_model_id(cells[0])
    # A "> 512k" tier is a secondary row for the same model id.
    if not model_id or ">" in _strip(cells[0]) or model_id in result:
        return
    input_price = _last_price(cells[1])
    output_price = _last_price(cells[2])
    if input_price is None or output_price is None:
        return
    result[model_id] = {"input": input_price, "output": output_price}


def _collect_tts(cells: list[str], result: dict[str, dict]) -> None:
    model_id = None
    for cell in cells:
        match = _SPEECH_MODEL.search(_strip(cell))
        if match:
            model_id = match.group(1)
            break
    if not model_id:
        return
    price_cell = next((c for c in cells if "characters" in c and "$" in c), None)
    price = _last_price(price_cell) if price_cell else None
    if price is not None:
        _store_specialty(result, model_id, price)


def _collect_music(cells: list[str], result: dict[str, dict]) -> None:
    if not any("Music-" in _strip(c) for c in cells):
        return
    price_cell = next(
        (c for c in cells if "$" in c and ("minutes" in c or "/up-to" in c)), None
    )
    price = _last_price(price_cell) if price_cell else None
    if price is not None:
        _store_specialty(result, "Music-3.0", price)


def _collect_image(cells: list[str], result: dict[str, dict]) -> None:
    if not any(_strip(c).startswith("image-") for c in cells):
        return
    price_cell = next((c for c in cells if "per image" in c and "$" in c), None)
    price = _last_price(price_cell) if price_cell else None
    if price is not None:
        _store_specialty(result, "image-01", price)


def fetch_minimax_catalog() -> dict[str, dict]:
    """Return live MiniMax prices keyed by catalog model id."""
    markdown = _fetch(PRICING_URL)
    result: dict[str, dict] = {}
    for cells in _table_rows(markdown):
        _collect_text(cells, result)
        _collect_tts(cells, result)
        _collect_music(cells, result)
        _collect_image(cells, result)
    if not result:
        raise RuntimeError("no MiniMax prices found in official docs")
    return result


if __name__ == "__main__":
    import json

    print(json.dumps(fetch_minimax_catalog(), ensure_ascii=False, indent=2))
