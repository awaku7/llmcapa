"""Scrape DeepSeek pricing from the official documentation."""
from __future__ import annotations

import json
import re
import sys
import traceback
from html import unescape
from urllib.request import Request, urlopen

try:
    from playwright.sync_api import sync_playwright
except ImportError:  # Playwright is optional; urllib is the first path.
    sync_playwright = None

PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing/"
THINKING_URL = "https://api-docs.deepseek.com/guides/thinking_mode/"


def _number(value: str) -> float | None:
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", value.replace(",", ""))
    return float(match.group(1)) if match else None


def _tokens(value: str) -> int:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KM]?)", value.upper())
    if not match:
        return 0
    multiplier = {"K": 1_000, "M": 1_000_000}.get(match.group(2), 1)
    return int(float(match.group(1)) * multiplier)


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"<[^>]+>", "\n", html)
    return unescape(text)


def parse_pricing_text(text: str) -> dict[str, dict]:
    """Extract model names and peak prices from rendered pricing text."""
    # Restrict model discovery to the model header. Footnotes also mention
    # retired aliases, which must not become active pricing columns.
    model_header = text.split("BASE URL", 1)[0]
    model_ids = list(
        dict.fromkeys(
            re.findall(r"(?i)\bdeepseek-[a-z0-9]+(?:-[a-z0-9]+)*", model_header)
        )
    )
    normalized = re.sub(r"\s+", " ", text)
    feature_text = normalized.split("FEATURES", 1)[-1].split("PRICING", 1)[0]
    feature_labels = (
        "Json Output",
        "Tool Calls",
        "Responses API",
        "Anthropic API",
        "FIM Completion（Beta）",
        "Vision",
    )

    def feature_values(label: str) -> list[str]:
        labels = "|".join(re.escape(item) for item in feature_labels)
        match = re.search(
            rf"{re.escape(label)}\s+(.*?)(?=(?:{labels})|$)",
            feature_text,
            re.I,
        )
        return (
            re.findall(r"✓|Not supported|Non-thinking mode only", match.group(1))
            if match
            else []
        )

    pricing_text = text.split("PRICING", 1)[-1]
    prices = [
        float(value)
        for value in re.findall(r"\$\s*([0-9]+(?:\.[0-9]+)?)", pricing_text)
    ]
    # Prices are arranged by row and model column: cache-hit off-peak,
    # cache-hit peak, cache-miss off-peak, cache-miss peak, output off-peak,
    # and output peak. Select the current peak cache-miss input and output
    # rows based on the number of model columns rather than hard-coded IDs.
    model_count = len(model_ids)
    required_prices = model_count * 6
    input_start = model_count * 3
    output_start = model_count * 5
    def row(start: int) -> list[float]:
        return (
            prices[start : start + model_count]
            if len(prices) >= required_prices
            else []
        )

    cache_hit_off_peak = row(0)
    cache_hit_peak = row(model_count)
    input_off_peak = row(model_count * 2)
    input_prices = row(input_start)
    output_off_peak = row(model_count * 4)
    output_prices = row(output_start)
    context_match = re.search(
        r"CONTEXT LENGTH\s+([0-9.]+\s*[KM])", text, re.I
    )
    max_output_match = re.search(
        r"MAX(?:IMUM)?[:\s]+([0-9.]+\s*[KM])", text, re.I
    )
    versions_match = re.search(
        r"MODEL VERSION\s+([A-Za-z0-9._-]+)\s+([A-Za-z0-9._-]+)",
        text,
        re.I,
    )
    versions = list(versions_match.groups()) if versions_match else []
    concurrency_text = re.sub(
        r"Concurrency Limit\s*\([^)]*\)", "Concurrency Limit", text, flags=re.I
    )
    concurrency_match = re.search(
        r"Concurrency Limit[^0-9]*([0-9]+)[^0-9]+([0-9]+)",
        concurrency_text,
        re.I,
    )
    concurrency = (
        [int(value) for value in concurrency_match.groups()]
        if concurrency_match
        else []
    )
    legacy_match = re.search(
        r"legacy names (.*?) are still accepted", normalized, re.I
    )
    legacy_aliases = (
        re.findall(r"\bdeepseek-[a-z0-9]+(?:-[a-z0-9]+)*", legacy_match.group(1))
        if legacy_match
        else []
    )
    supports_reasoning = bool(
        re.search(r"THINKING MODE .*?Supports both", normalized, re.I)
    )
    result: dict[str, dict] = {}
    for index, model_id in enumerate(model_ids):
        if index >= len(input_prices) or index >= len(output_prices):
            break
        result[model_id.lower()] = {
            "input": input_prices[index],
            "output": output_prices[index],
            "cache_hit": cache_hit_peak[index],
            "off_peak": {
                "input": input_off_peak[index],
                "output": output_off_peak[index],
                "cache_hit": cache_hit_off_peak[index],
            },
            "ctx": _tokens(context_match.group(1)) if context_match else 0,
            "max_out": _tokens(max_output_match.group(1)) if max_output_match else 0,
            "version": versions[index] if index < len(versions) else "",
            "concurrency": concurrency[index] if index < len(concurrency) else 0,
            "aliases": legacy_aliases if index == 0 else [],
            "supports_json_mode": feature_values("Json Output")[index:index + 1] == ["✓"],
            "supports_function_calling": feature_values("Tool Calls")[index:index + 1] == ["✓"],
            "supports_responses_api": feature_values("Responses API")[index:index + 1] == ["✓"],
            "supports_anthropic_api": feature_values("Anthropic API")[index:index + 1] == ["✓"],
            "supports_fim": (
                feature_values("FIM Completion（Beta）")[index:index + 1]
                not in ([], ["Not supported"])
            ),
            "supports_vision": feature_values("Vision")[index:index + 1] == ["✓"],
            "supports_reasoning": supports_reasoning,
        }
    return result


def fetch_official_text(url: str) -> str:
    """Fetch an official page, falling back to Playwright if needed."""
    request = Request(url, headers={"User-Agent": "llmcapa catalog updater"})
    try:
        with urlopen(request, timeout=30) as response:
            text = _html_to_text(response.read().decode("utf-8", errors="replace"))
        if text.strip():
            return text
    except Exception:
        pass

    if sync_playwright is None:
        raise RuntimeError(
            f"official page could not be fetched and Playwright is unavailable: {url}"
        )
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)
            return page.inner_text("body")
        finally:
            browser.close()


def fetch_pricing_text() -> str:
    return fetch_official_text(PRICING_URL)


def scrape_pricing() -> dict[str, dict]:
    result = parse_pricing_text(fetch_pricing_text())
    if not result:
        raise RuntimeError("no model pricing was found on the official DeepSeek page")

    thinking_text = re.sub(r"\s+", " ", fetch_official_text(THINKING_URL))
    effort_match = re.search(
        r"reasoning_effort[^a-z]+(low/high/max)", thinking_text, re.I
    )
    effort_values = (
        list(dict.fromkeys(re.findall(r"low|high|max", effort_match.group(1), re.I)))
        if effort_match
        else []
    )
    for row in result.values():
        row["supports_reasoning_effort"] = bool(effort_values)
        row["reasoning_effort_values"] = effort_values
    return result


if __name__ == "__main__":
    try:
        extracted_pricing = scrape_pricing()
        print(
            json.dumps(
                {
                    "deepseek_scraped": bool(extracted_pricing),
                    "extracted_pricing": extracted_pricing,
                },
                ensure_ascii=False,
            )
        )
    except Exception as exc:
        print(
            json.dumps(
                {"error": str(exc), "traceback": traceback.format_exc()},
                ensure_ascii=False,
            )
        )
        sys.exit(1)
