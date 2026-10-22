"""Guard against OpenAI official-pricing table column reordering and omissions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _update_openai as updater


def test_prices_are_read_by_header_not_by_column_position():
    text = """| Model | Input | Cached input | Output |
| --- | --- | --- | --- |
| gpt-4o | $2.50 | $1.25 | $10.00 |
| gpt-mini | $0.25 | $0.10 | $2.00 |

| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| gpt-sol | $4.00 | $20.00 | $1.00 |
"""
    assert updater.prices(text) == {
        "gpt-4o": (2.5, 10.0),
        "gpt-mini": (0.25, 2.0),
        "gpt-sol": (4.0, 20.0),
    }
    assert updater.parse_pricing_table(text)["gpt-sol"]["cached_input_per_1m"] == 1


def test_life_sciences_rates_follow_headings_even_if_reordered():
    markdown = """Life sciences models

Access is limited to approved users.

| Model | Input | Output | Cached input |
| --- | --- | --- | --- |
| gpt-rosalind-research | $5.00 | $25.00 | $0.50 |
| gpt-rosalind-discovery | $5.00 | $25.00 | $0.50 |

Multimodal models
"""
    entries = updater.parse_life_sciences_models(markdown)
    assert len(entries) == 2
    for entry in entries:
        assert entry["input_per_1m"] == 5.0
        assert entry["output_per_1m"] == 25.0
        assert entry["cached_input_per_1m"] == 0.5
        assert entry["required_approval"] is True


def test_missing_price_table_does_not_erase_known_rate(tmp_path, monkeypatch):
    path = tmp_path / "openai.json"
    path.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o",
                        "pricing": {
                            "input_per_1m": 2.5,
                            "output_per_1m": 10.0,
                            "currency": "USD",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "DATA", path)
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(
        updater,
        "fetch",
        lambda url: (
            "- [GPT-4o](/api/docs/models/gpt-4o.md)\n"
            if url == updater.MODELS_URL
            else "# Price table temporarily unavailable"
        ),
    )
    monkeypatch.setattr(
        updater,
        "detail",
        lambda _path: {"provider": "openai", "model_id": "gpt-4o", "extra": {}},
    )
    updater.main()
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["models"][0]["pricing"]["input_per_1m"] == 2.5
    assert updated["models"][0]["pricing"]["output_per_1m"] == 10.0
def test_openai_refresh_writes_cached_input_rates_to_existing_and_new_models(
    tmp_path, monkeypatch
):
    catalog = tmp_path / "openai.json"
    catalog.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "openai",
                        "model_id": "gpt-4o",
                        "extra": {"cached_input_per_1m": 1.4},
                        "pricing": {
                            "input_per_1m": 2.5,
                            "output_per_1m": 10.0,
                            "currency": "USD",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    index = (
        "- [GPT-4o](/api/docs/models/gpt-4o.md)\n"
        "- [GPT-mini](/api/docs/models/gpt-mini.md)\n"
    )
    pricing = (
        "| Model | Input | Output | Cached input |\n"
        "| --- | --- | --- | --- |\n"
        "| gpt-4o | $2.50 | $10.00 | $1.25 |\n"
        "| gpt-mini | $0.25 | $2.00 | $0.10 |\n"
    )
    monkeypatch.setattr(updater, "ROOT", tmp_path)
    monkeypatch.setattr(updater, "DATA", catalog)
    monkeypatch.setattr(
        updater,
        "fetch",
        lambda url: index if url == updater.MODELS_URL else pricing,
    )
    monkeypatch.setattr(
        updater,
        "detail",
        lambda path: {
            "provider": "openai",
            "model_id": path.rsplit("/", 1)[-1].removesuffix(".md"),
            "extra": {},
        },
    )
    updater.main()
    models = {
        model["model_id"]: model
        for model in json.loads(catalog.read_text(encoding="utf-8"))["models"]
    }
    assert models["gpt-4o"]["extra"]["cached_input_per_1m"] == 1.25
    assert models["gpt-mini"]["extra"]["cached_input_per_1m"] == 0.10
    assert models["gpt-mini"]["pricing"]["output_per_1m"] == 2.0
