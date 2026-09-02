"""Fetch and parse the official xAI model/pricing documentation.

The previous scraper captured the rendered page text but did not produce the
structured ListModels shape consumed by the updater. This version parses the
official Markdown endpoint directly and writes a compatible snapshot.
"""
from __future__ import annotations

import json
import re
import ssl
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "_scratch_xai_listmodels_parsed.json"
SOURCE = "https://docs.x.ai/developers/models.md"


def fetch() -> str:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-xai-updater/1.0"})
    with urlopen(req, timeout=30, context=ssl.create_default_context()) as response:
        return response.read().decode("utf-8")


def context_tokens(value: str) -> int:
    value = value.strip().upper()
    m = re.search(r"([\d.]+)\s*([KM]?)", value)
    if not m:
        return 0
    n = float(m.group(1))
    return int(n * (1_000_000 if m.group(2) == "M" else 1_000 if m.group(2) == "K" else 1))


def parse(text: str) -> list[dict]:
    rows = []
    in_table = False
    for line in text.splitlines():
        if line.strip() == "| Model | Context | Input / 1M tokens | Cached input / 1M tokens | Output / 1M tokens |":
            in_table = True
            continue
        if in_table and not line.strip().startswith("|"):
            if rows:
                break
            continue
        if not in_table or line.strip().startswith("| ---"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        model = re.sub(r"\s*\([^)]*\)\s*$", "", cells[0]).strip()
        if not model or model.lower() == "model":
            continue
        price = lambda s: float(re.search(r"[\d.]+", s.replace(",", "")).group()) if re.search(r"[\d.]+", s) else None
        rows.append({
            "name": model,
            "inputModalities": [1, 2],
            "outputModalities": [1],
            "maxPromptLength": context_tokens(cells[1]),
            "maxCompletionLength": 0,
            "promptTextTokenPrice": price(cells[2]),
            "cachedPromptTokenPrice": price(cells[3]),
            "completionTextTokenPrice": price(cells[4]),
        })
    unique = {}
    for row in rows:
        unique.setdefault(row["name"], row)
    return list(unique.values())


def main() -> None:
    models = parse(fetch())
    if not models:
        raise SystemExit("xAI official model table was not found")
    OUT.write_text(json.dumps(models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(models)} official text models")


if __name__ == "__main__":
    main()
