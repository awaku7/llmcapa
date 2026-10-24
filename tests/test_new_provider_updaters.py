from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name: str):
    path = SCRIPTS / f"_{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_laya_parsers_extract_package_and_hub_inventory():
    updater = _load("update_laya")
    assert updater.parse_package_version({"info": {"version": "0.4.0"}}) == "0.4.0"
    assert updater.parse_hf_model_ids(
        [
            {"modelId": "convaiinnovations/laya"},
            {"modelId": "convaiinnovations/laya-multilingual"},
        ]
    ) == {"convaiinnovations/laya", "convaiinnovations/laya-multilingual"}


def test_liquid_parsers_only_read_decision_rows_and_explicit_specs():
    updater = _load("update_liquid")
    matrix = """| **Text-to-text Models** | | | |
| [LFM2.5-1.2B](/lfm/models/lfm25-1.2b) | LFM2.5 | [✓](https://huggingface.co/LiquidAI/LFM2.5-1.2B) | — |
| **Decision Models** | | | |
| [d1-3B](/lfm/models/d1-3b) | d1 (Latest release) | [✓](https://huggingface.co/LiquidAI/d1-3B) | [✓](https://huggingface.co/LiquidAI/d1-3B-GGUF) |
| [d1-omni-600M](/lfm/models/d1-omni-600m) | d1 | [✓](https://huggingface.co/LiquidAI/d1-omni-600M) | — |
| [d1](/lfm/models/d1) | d1 | API | — |
Looking for an older model?
"""
    records = updater.parse_decision_models(matrix)
    assert [row["model_id"] for row in records] == ["d1-3B", "d1-omni-600M", "d1"]
    assert records[0]["huggingface_model"] == "https://huggingface.co/LiquidAI/d1-3B"
    assert records[2]["hosted_api"] is True

    specs = updater.parse_model_specs(
        "| Parameters | 3.12B |\n| Context Length | 32K tokens |\nText + audio (up to 30 s)"
    )
    assert specs["parameters"] == 3_120_000_000
    assert specs["context_window"] == 32_768
    assert specs["audio_max_duration_seconds"] == 30


def test_modellix_llm_parser_normalizes_modalities_and_tiered_prices():
    updater = _load("update_modellix")
    rows = updater.parse_table_rows(
        [
            {
                "model_id": "anthropic/claude-haiku-5.5",
                "display_name": "Claude Haiku 5.5",
                "input_modalities": ["Text", "Image"],
                "output_modalities": ["Text"],
                "context_window": "1M",
                "price_tiers": [
                    {
                        "input_context": "≤ 100K",
                        "input_per_1m": 0.09,
                        "output_per_1m": 0.45,
                    },
                    {
                        "input_context": "> 100K",
                        "input_per_1m": 0.45,
                        "output_per_1m": 2.25,
                    },
                ],
            }
        ]
    )
    assert rows[0]["context_window"] == 1_000_000
    assert rows[0]["input_modalities"] == ["text", "image"]
    assert len(rows[0]["price_tiers"]) == 2


def test_modellix_media_classification_requires_a_clear_task():
    updater = _load("update_modellix_media")
    t2v = updater.classify_task(
        "alibaba/happyhorse-1-1-t2v",
        "HappyHorse 1.1 T2V",
        "[Core Function] Text-to-video generation model.",
    )
    assert t2v == {
        "input_modalities": ["text"],
        "output_modalities": ["video"],
        "media_model_type": "text-to-video",
    }
    rows, skipped = updater.parse_catalog_index(
        "- [HappyHorse 1.1 T2V](https://docs.modellix.ai/alibaba/happyhorse-1-1-t2v.md): [Core Function] Text-to-video generation model.\n"
        "- [Unknown model](https://docs.modellix.ai/vendor/unknown.md): [Core Function] A model for an undocumented task.\n"
    )
    assert rows[0]["model_id"] == "alibaba/happyhorse-1-1-t2v"
    assert skipped == ["vendor/unknown"]

    assert (
        updater.classify_task(
            "minimax/minimax-h3-max-fl2v",
            "MiniMax H3 Max FL2V",
            "[Core Function] Video from first and last frames.",
        )["media_model_type"]
        == "image-to-video"
    )
    assert (
        updater.classify_task(
            "kling/kling-video-o1",
            "Kling Video O1",
            "[Core Function] Video editing from a reference video.",
        )["media_model_type"]
        == "video-to-video"
    )
    assert updater.classify_task(
        "alibaba/cosyvoice-clone",
        "CosyVoice Clone",
        "[Core Function] Clones a speaker from reference audio and synthesizes speech.",
    )["output_modalities"] == ["audio"]


def test_perplexity_router_parser_reads_only_official_hosted_route_prices():
    updater = _load("update_perplexity_router")
    docs = """## Perplexity-Hosted Models
| Model | Input ($/1M) | Output ($/1M) | Cache read ($/1M) | Docs |
| - | -: | -: | -: | - |
| **`perplexity/kimi-k3`** | 3.00 | 15.00 | 0.30 | [Kimi](https://huggingface.co/moonshotai/Kimi-K3) |
"""
    rows = updater.parse_model_table(docs)
    assert rows == [
        {
            "provider": "perplexity-router",
            "model_id": "perplexity/kimi-k3",
            "display_name": "Perplexity Router: Kimi",
            "input_per_1m": 3.0,
            "output_per_1m": 15.0,
            "cache_read_per_1m": 0.3,
            "native_model_source": "https://huggingface.co/moonshotai/Kimi-K3",
            "native_provider": "moonshotai",
        }
    ]
    record = updater._base_record(rows[0], None, "2026-10-12")
    assert record["supports_responses_api"] is True
    assert record["supports_streaming"] is True
    assert record["extra"]["responses_endpoint"].endswith("/responses")
    new_record = updater._base_record(rows[0], None, "2026-10-12")
    assert new_record["context_window"] == 0
    assert new_record["max_output_tokens"] == 0


def test_typesafe_parser_tracks_current_version_aliases_and_limits():
    updater = _load("update_typesafe")
    docs = """## Current models
| Jev 1.13 | `jev-1.13.0` |
| :- | :- |
| Price (per Btok / per Mtok) | $42 / $0.042 |
| Context length | 64k tokens; 32k tokens for `state` plus the longest question |
| Input | Text only. |
## Aliases
| Alias | Points to | Meaning |
| :- | :- | :- |
| `jev-latest` | `jev-1.13.0` | Latest stable |
| `jev-preview` | `jev-1.13.0` | Preview alias |
Rate limits 100K tokens per second / 80 requests per second.
"""
    snapshot = updater.parse_model_snapshot(docs)
    assert snapshot["model_id"] == "jev-1.13.0"
    assert snapshot["context_window"] == 64_000
    assert snapshot["max_state_tokens"] == 32_000
    assert snapshot["input_per_1m"] == 0.042
    assert set(snapshot["aliases"]) == {"jev-latest", "jev-preview"}
    assert snapshot["rate_limits"] == {
        "tokens_per_second": 100_000,
        "requests_per_minute": 4_800,
    }


def test_typesafe_parser_handles_current_wide_version_table_and_alias_moves():
    updater = _load("update_typesafe")
    docs = r"""## Current models
| | Jev 1.14 | Jev 1.13 |
| :- | :- | :- |
| Model ID | `jev-1.14.0` | `jev-1.13.0` |
| Price (per Btok / per Mtok) | \$42 / \$0.042 | \$42 / \$0.042 |
| Context length | 64k per-request / 32k per-question | 64k per-request / 32k per-question |
## Aliases
| Alias | Points to | Meaning |
| :- | :- | :- |
| `jev-latest` | `jev-1.13.0` | Stable |
| `jev-preview` | `jev-1.14.0` | Newest |
"""
    snapshots = updater.parse_model_snapshots(docs)
    assert [item["model_id"] for item in snapshots] == ["jev-1.14.0", "jev-1.13.0"]
    assert snapshots[0]["context_window"] == snapshots[1]["context_window"] == 64_000
    assert (
        snapshots[0]["max_state_tokens"] == snapshots[1]["max_state_tokens"] == 32_000
    )
    assert snapshots[0]["input_per_1m"] == snapshots[1]["input_per_1m"] == 0.042
    assert snapshots[0]["aliases"] == ["jev-preview"]
    assert snapshots[1]["aliases"] == ["jev-latest"]

    merged = updater.merge_catalog(
        snapshots,
        [
            {
                "provider": "typesafe",
                "model_id": "jev-1.13.0",
                "aliases": ["jev-latest", "jev-preview"],
            }
        ],
        "2026-10-15",
    )
    assert merged[0]["model_id"] == "jev-1.14.0"
    assert merged[0]["aliases"] == ["jev-preview"]
    assert merged[1]["model_id"] == "jev-1.13.0"
    assert merged[1]["aliases"] == ["jev-latest", "jev-1.13"]
