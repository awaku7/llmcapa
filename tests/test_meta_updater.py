from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import _update_meta


def test_meta_parser_handles_current_models_page_prose() -> None:
    text = (
        "Muse Wonder takes text, image, video, audio, and PDF input, returns text, "
        "has a 1,048,576-token context window. Model: muse-wonder-1.0. "
        "Muse Spark comes in versions. All take text, image, video, audio, and PDF "
        "input, return text, and have a 1,048,576-token context window. "
        "Muse Spark 1.3 (muse-spark-1.3) muse-spark-1.3-contributor "
        "muse-spark-1.2 muse-spark-1.2-contributor muse-spark-1.1"
    )

    models = _update_meta.parse_models_page(text)

    assert models["muse-wonder-1.0"]["context"] == 1_048_576
    assert models["muse-wonder-1.0"]["input"] == "Text, image, video, audio, and PDF"
    assert models["muse-spark-1.3"]["context"] == 1_048_576
    assert models["muse-spark-1.3-contributor"]["context"] == 1_048_576


def test_meta_pricing_parser_handles_current_per_mode_tables() -> None:
    text = (
        "Model pricing Muse Wonder Model: muse-wonder-1.0. "
        "Usage Standard mode (per 1M tokens) Contributor mode (per 1M tokens) "
        "Cached input $0.20 Not available Input $4.00 Not available "
        "Output $20.00 Not available Muse Spark Models: muse-spark-1.3 "
        "Usage Standard mode (per 1M tokens) Contributor mode (per 1M tokens) "
        "Cached input $0.15 $0.002 Input $1.25 $0.10 Output $4.25 $0.20 "
        "Token pricing notes"
    )

    prices = _update_meta.parse_pricing(text)

    assert prices["wonder"] == {
        "cached_input": 0.20,
        "input": 4.0,
        "output": 20.0,
    }
    assert prices["standard"] == {
        "cached_input": 0.15,
        "input": 1.25,
        "output": 4.25,
    }
    assert prices["contributor"] == {
        "cached_input": 0.002,
        "input": 0.10,
        "output": 0.20,
    }
