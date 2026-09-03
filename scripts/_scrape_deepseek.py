"""Playwright: scrape DeepSeek pricing from official docs."""
import json
import re
import sys
import traceback

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print('{"error":"playwright not installed"}')
    sys.exit(1)

def _number(value: str) -> float | None:
    match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)", value.replace(",", ""))
    return float(match.group(1)) if match else None


def _tokens(value: str) -> int:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([KM]?)", value.upper())
    if not match:
        return 0
    multiplier = {"K": 1_000, "M": 1_000_000}.get(match.group(2), 1)
    return int(float(match.group(1)) * multiplier)


def parse_pricing_text(text: str) -> dict[str, dict]:
    """Extract model names and prices from the rendered pricing page text."""
    model_ids = list(
        dict.fromkeys(
            re.findall(r"(?i)\bdeepseek-[a-z0-9]+(?:-[a-z0-9]+)*", text)
        )
    )
    pricing_text = text.split("PRICING", 1)[-1]
    prices = [
        float(value)
        for value in re.findall(
            r"\$\s*([0-9]+(?:\.[0-9]+)?)", pricing_text
        )
    ]
    # The page lists three models by column. Prefer peak cache-miss input and
    # peak output prices; if the layout changes, retain a safe fallback.
    input_prices = prices[9:12] if len(prices) >= 18 else []
    output_prices = prices[15:18] if len(prices) >= 18 else []
    context_match = re.search(
        r"CONTEXT LENGTH\s+([0-9.]+\s*[KM])", text, re.I
    )
    max_output_match = re.search(
        r"MAX(?:IMUM)?[:\s]+([0-9.]+\s*[KM])", text, re.I
    )
    result: dict[str, dict] = {}
    for index, model_id in enumerate(model_ids):
        if index >= len(input_prices) or index >= len(output_prices):
            break
        result[model_id.lower()] = {
            "input": input_prices[index],
            "output": output_prices[index],
            "ctx": _tokens(context_match.group(1)) if context_match else 0,
            "max_out": _tokens(max_output_match.group(1)) if max_output_match else 0,
        }
    return result


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://api-docs.deepseek.com/quick_start/pricing", wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(5000)
        text = page.inner_text("body")
        browser.close()

        extracted_pricing = parse_pricing_text(text)
        result = {
            "deepseek_scraped": bool(extracted_pricing),
            "page_len": len(text),
            "extracted_pricing": extracted_pricing,
        }
        print(json.dumps(result, ensure_ascii=False))
except Exception as e:
    print(json.dumps({"error": str(e), "traceback": traceback.format_exc()}, ensure_ascii=False))
