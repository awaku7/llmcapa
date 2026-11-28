from __future__ import annotations

import importlib.util
import json
import sys
import types
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


def test_ollama_command_a_limits_use_current_library_snapshot():
    updater = _load("update_ollama")
    models = [
        {
            "provider": "ollama",
            "model_id": "command-a:latest",
            "context_window": 131_072,
            "max_output_tokens": 32_768,
            "extra": {"custom": "keep"},
        },
        {
            "provider": "ollama",
            "model_id": "deepseek-r1",
            "context_window": 131_072,
            "max_output_tokens": 32_768,
        },
        {
            "provider": "ollama",
            "model_id": "deepseek-r1:671b",
            "context_window": 131_072,
            "max_output_tokens": 32_768,
        },
    ]

    updater.apply_verified_model_specs(models)

    assert models[0]["context_window"] == 16_384
    assert models[0]["max_output_tokens"] == 0
    assert models[0]["extra"]["model_max_context_window"] == 256_000
    assert models[0]["extra"]["context_window_source"] == (
        "https://ollama.com/library/command-a"
    )
    assert models[0]["extra"]["custom"] == "keep"
    assert models[1]["context_window"] == 128_000
    assert models[1]["max_output_tokens"] == 0
    assert models[2]["context_window"] == 160_000
    assert models[2]["max_output_tokens"] == 0


def test_together_updater_adds_current_versioned_deepseek_v4_pro():
    updater = _load("update_together")
    models = []

    updater.apply_verified_model_specs(models, checked_at="2026-11-02")
    updater.apply_verified_model_specs(models, checked_at="2026-11-02")

    assert len(models) == 2
    by_id = {model["model_id"]: model for model in models}
    historical = by_id["deepseek-ai/DeepSeek-V4-Pro"]
    assert historical["context_window"] == 512_000
    assert historical["max_output_tokens"] == 0
    assert historical["pricing"] == {
        "input_per_1m": 2.10,
        "output_per_1m": 4.40,
        "currency": "USD",
    }
    assert historical["extra"]["model_listing_status"] == "historical_changelog_entry"

    current = by_id["deepseek-ai/DeepSeek-V4-Pro-0813"]
    assert current["context_window"] == 1_048_576
    assert current["max_output_tokens"] == 0
    assert current["pricing"] == {
        "input_per_1m": 1.32,
        "output_per_1m": 3.96,
        "currency": "USD",
    }
    assert current["extra"]["cached_input_per_1m"] == 0.13
    assert current["extra"]["official_model_specs_source"] == (
        "https://docs.together.ai/docs/serverless/models"
    )


def test_vercel_gateway_limits_follow_published_deepseek_routes():
    updater = _load("update_vercel")
    models = [
        {
            "provider": "vercel",
            "model_id": "DeepSeek-R1",
            "context_window": 163_840,
            "max_output_tokens": 163_840,
            "extra": {},
        },
        {
            "provider": "vercel",
            "model_id": "deepseek-ai/DeepSeek-V4-Pro",
            "context_window": 512_000,
            "max_output_tokens": 1024,
            "extra": {},
        },
    ]

    updater.apply_verified_model_specs(models)

    assert models[0]["context_window"] == 160_000
    assert models[0]["max_output_tokens"] == 16_000
    assert models[0]["extra"]["gateway_provider_limits"]["Bedrock"] == {
        "context_window": 128_000,
        "max_output_tokens": 8_000,
    }
    assert models[1]["context_window"] == 512_000
    assert models[1]["max_output_tokens"] == 0


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
        "- [HappyHorse 1.1 T2V](https://docs.modellix.ai/alibaba/happyhorse-1-1-t2v.md): Alibaba's text-to-video model with native sound.\n"
        "- [Unknown model](https://docs.modellix.ai/vendor/unknown.md): [Core Function] A model for an undocumented task.\n"
        "- [Choose the Right Model](https://docs.modellix.ai/get-started/model-select.md): Choose an image, video, or speech model.\n"
        "- [Live Overview](https://docs.modellix.ai/live/overview.md): Realtime voice transcription and audio understanding.\n"
    )
    assert rows[0]["model_id"] == "alibaba/happyhorse-1-1-t2v"
    assert skipped == ["vendor/unknown"]
    assert (
        updater.merge_catalog([], [{"model_id": "live/overview"}], "2026-11-17") == []
    )

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
            "context_window": 0,
            "max_output_tokens": 0,
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


def test_perplexity_orchestrator_parser_reads_current_perplexity_tab_only():
    updater = _load("update_perplexity_router")
    docs = """## Available Models
> [tab] Anthropic
> | `anthropic/claude` | Tier 1 | 200,000 | 64,000 | 1.00 | 5.00 | 0.10 |

> [tab] Z.AI
>
> | Model | Usage tier | Context window | Max output | Input ($/1M) | Output ($/1M) | Cache read ($/1M) |
> | - | - | -: | -: | -: | -: | -: |
> | `perplexity/glm-5.3` | Tier 0 | 1,000,000 | 131,072 | 1.40 | 4.40 | 0.26 |
> | `zai/glm` | Tier 0 | 100,000 | 10,000 | 1.00 | 1.00 | 0.10 |

> [tab] Moonshot AI
> | `perplexity/kimi-k3` | Tier 0 | 1,048,576 | 131,072 | 3.00 | 15.00 | 0.30 |

## Access by Usage Tier
"""
    rows = updater.parse_model_table(docs)
    assert {row["model_id"] for row in rows} == {
        "perplexity/kimi-k3",
        "perplexity/glm-5.3",
    }
    by_id = {row["model_id"]: row for row in rows}
    assert by_id["perplexity/kimi-k3"]["context_window"] == 1_048_576
    assert by_id["perplexity/kimi-k3"]["max_output_tokens"] == 131_072
    assert by_id["perplexity/kimi-k3"]["input_per_1m"] == 3.0
    assert by_id["perplexity/glm-5.3"]["cache_read_per_1m"] == 0.26
    record = updater._base_record(by_id["perplexity/kimi-k3"], None, "2026-11-20")
    assert record["context_window"] == 1_048_576
    assert record["max_output_tokens"] == 131_072
    assert record["extra"]["orchestrator_api_base_url"].endswith("/orchestrator/v1")


def test_vertex_sdk_discovery_includes_documented_gemini4_variants(monkeypatch):
    updater = _load("update_vertex_ai")
    vertexai = types.ModuleType("vertexai")
    vertexai.model_garden = types.SimpleNamespace(
        list_deployable_models=lambda **_: [f"sdk-model-{index}" for index in range(20)]
    )
    monkeypatch.setitem(sys.modules, "vertexai", vertexai)

    discovered = dict(updater.discover_models())
    expected = {
        "gemini-4-argon",
        "gemini-4-carbon",
        "gemini-4-hydrogen",
        "gemini-4-neon",
    }
    assert expected <= discovered.keys()
    assert set(updater.VERTEX_GEMINI_MODEL_PAGE_SPECS) <= discovered.keys()

    for model_id, modalities in (
        ("gemini-4-argon", ["image", "audio", "video", "file"]),
        ("gemini-4-carbon", ["image", "audio", "video", "file"]),
        ("gemini-4-hydrogen", ["image", "audio", "video", "file"]),
        ("gemini-4-neon", ["image", "audio", "video", "file"]),
    ):
        row = updater.minimal(model_id, discovered[model_id])
        updater.enrich_thinking(row)
        updater.enrich_vertex_gemini_modalities(row)
        updater.apply_vertex_gemini_model_page_spec(row)
        assert row["supports_reasoning"] is True
        assert set(modalities) <= set(row["input_modalities"])
        assert row["supports_vision"] is True
        assert row["supports_audio_input"] is True
        assert row["audio"]["accepts_audio_input"] is True
        assert row["video"]["accepts_video_input"] is True


def test_vertex_ai_catalog_contains_all_documented_gemini4_variants():
    path = ROOT / "src" / "llmcapa" / "data" / "vertex-ai.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["models"]
    model_ids = {row.get("model_id") for row in rows}
    assert {
        "gemini-4-argon",
        "gemini-4-carbon",
        "gemini-4-hydrogen",
        "gemini-4-neon",
    } <= model_ids

    by_id = {row["model_id"]: row for row in rows}
    for model_id in (
        "gemini-4-argon",
        "gemini-4-carbon",
        "gemini-4-hydrogen",
        "gemini-4-neon",
    ):
        assert {"image", "audio", "file", "video"} <= set(
            by_id[model_id]["input_modalities"]
        )
        assert by_id[model_id]["supports_vision"] is True
        assert by_id[model_id]["supports_audio_input"] is True
        assert by_id[model_id]["audio"]["accepts_audio_input"] is True
        assert by_id[model_id]["video"]["accepts_video_input"] is True
        assert by_id[model_id]["max_output_tokens"] == 65_536
        assert by_id[model_id]["extra"]["long_decode_max_output_tokens"] == 1_048_576


def test_vertex_ai_catalog_covers_official_gemini_model_pages():
    updater = _load("update_vertex_ai")
    path = ROOT / "src" / "llmcapa" / "data" / "vertex-ai.json"
    rows = {
        row["model_id"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))["models"]
    }
    specs = updater.VERTEX_GEMINI_MODEL_PAGE_SPECS

    assert set(specs) <= rows.keys()
    for model_id, spec in specs.items():
        row = rows[model_id]
        assert row["context_window"] == spec["context_window"], model_id
        assert row["max_output_tokens"] == spec["max_output_tokens"], model_id
        assert row["input_modalities"] == spec["input_modalities"], model_id
        assert row["output_modalities"] == spec["output_modalities"], model_id
        assert row["extra"]["vertex_model_page_source"] == spec["source"], model_id

    assert rows["gemini-3.8-flash-cyber"]["pricing"] is None
    assert rows["gemini-live-2.5-flash-native-audio"]["context_window"] == 131_072
    assert rows["gemini-3.5-transcribe"]["context_window"] == 0
    assert rows["gemini-3.5-transcribe"]["input_modalities"] == ["audio"]


def test_vertex_gemini38_flash_matches_official_modality_and_thinking_specs():
    updater = _load("update_vertex_ai")
    model_id = "gemini-3.8-flash"
    row = updater.minimal(model_id, "Gemini 3.8 Flash")
    updater.enrich_thinking(row)
    updater.enrich_vertex_gemini_modalities(row)
    updater.apply_vertex_gemini_model_page_spec(row)

    assert set(row["input_modalities"]) == {
        "text",
        "image",
        "audio",
        "video",
        "file",
    }
    assert row["supports_vision"] is True
    assert row["supports_audio_input"] is True
    assert row["supports_audio_output"] is False
    assert row["audio"]["accepts_audio_input"] is True
    assert row["video"]["accepts_video_input"] is True
    assert row["thinking_level_values"] == ["low", "medium", "high"]

    path = ROOT / "src" / "llmcapa" / "data" / "vertex-ai.json"
    catalog = {
        item["model_id"]: item
        for item in json.loads(path.read_text(encoding="utf-8"))["models"]
    }
    saved = catalog[model_id]
    assert set(saved["input_modalities"]) == {
        "text",
        "image",
        "audio",
        "video",
        "file",
    }
    assert saved["supports_vision"] is True
    assert saved["audio"]["accepts_audio_input"] is True
    assert saved["video"]["accepts_video_input"] is True
    assert saved["thinking_level_values"] == ["low", "medium", "high"]


def test_google_gemini4_modalities_match_official_model_pages():
    updater = _load("update_google")
    expected_levels = {
        "gemini-4-argon": ["low", "medium", "high"],
        "gemini-4-carbon": ["low", "medium", "high"],
        "gemini-4-hydrogen": ["low", "medium", "high", "xhigh"],
        "gemini-4-neon": ["low", "medium", "high", "xhigh"],
    }
    path = ROOT / "src" / "llmcapa" / "data" / "google.json"
    rows = {row["model_id"]: row for row in json.loads(path.read_text(encoding="utf-8"))["models"]}

    for model_id, thinking_levels in expected_levels.items():
        template = updater.template_for(model_id)
        row = rows[model_id]
        expected_modalities = {"text", "image", "audio", "video", "file"}
        assert set(template["input_modalities"]) == expected_modalities
        assert template["thinking_level_values"] == thinking_levels
        assert set(row["input_modalities"]) == {
            "text",
            "image",
            "audio",
            "video",
            "file",
        }
        assert row["supports_vision"] is True
        assert row["supports_audio_input"] is True
        assert row["audio"]["accepts_audio_input"] is True
        assert row["video"]["accepts_video_input"] is True
        assert row["thinking_level_values"] == thinking_levels


def test_google_audio_models_use_documented_modalities_and_token_limits():
    updater = _load("update_google")
    path = ROOT / "src" / "llmcapa" / "data" / "google.json"
    rows = {
        row["model_id"]: row
        for row in json.loads(path.read_text(encoding="utf-8"))["models"]
    }

    for model_id in (
        "gemini-3.5-transcribe",
        "gemini-3.5-transcribe-live",
        "gemini-3.5-live-translate-preview",
    ):
        row = json.loads(json.dumps(rows[model_id]))
        updater.apply_google_gemini_audio_metadata(row)
        expected = updater.GOOGLE_GEMINI_AUDIO_MODEL_SPECS[model_id]
        assert row["input_modalities"] == expected["input_modalities"]
        assert row["output_modalities"] == expected["output_modalities"]
        assert row["context_window"] == expected["context_window"]
        assert row["max_output_tokens"] == expected["max_output_tokens"]
        assert row["supports_audio_input"] is True
        assert row["supports_audio_output"] == (
            "audio" in expected["output_modalities"]
        )
        assert row["audio"]["source_url"] == expected["source"]

    transcribe = rows["gemini-3.5-transcribe"]
    assert transcribe["input_modalities"] == ["audio"]
    assert transcribe["context_window"] == 0
    assert transcribe["max_output_tokens"] == 0
    live_translate = rows["gemini-3.5-live-translate-preview"]
    assert live_translate["input_modalities"] == ["audio"]
    assert live_translate["output_modalities"] == ["audio", "text"]
    assert live_translate["context_window"] == 131_072
    assert live_translate["max_output_tokens"] == 65_536


def test_google_gemini38_live_documents_video_frame_input_only():
    updater = _load("update_google")
    model_id = "gemini-3.8-live"
    catalog_path = ROOT / "src" / "llmcapa" / "data" / "google.json"
    catalog = {
        model["model_id"]: model
        for model in json.loads(catalog_path.read_text(encoding="utf-8"))["models"]
    }
    row = json.loads(json.dumps(catalog[model_id]))
    updater.apply_google_gemini_live_video_metadata(row)

    assert "video" in row["input_modalities"]
    assert "video" not in row["output_modalities"]
    assert row["supports_audio_input"] is True
    assert row["supports_audio_output"] is True
    assert row["video"]["accepts_video_input"] is True
    assert row["video"]["generation"] is False
    assert row["video"]["max_input_fps"] == 1
    assert row["video"]["input_mime_types"] == ["image/jpeg", "image/png"]
    assert row["video"]["source_url"] == (
        "https://ai.google.dev/gemini-api/docs/live-api/capabilities"
    )
    saved = catalog[model_id]
    assert "video" in saved["input_modalities"]
    assert "video" not in saved["output_modalities"]
    assert saved["video"]["accepts_video_input"] is True
    assert saved["video"]["generation"] is False


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


def test_openrouter_tool_search_is_provider_wide_and_limited_to_documented_apis():
    updater = _load("update_openrouter")
    routes = [{"model_id": "openai/gpt-5.4"}, {"model_id": "openrouter/auto"}]

    updater.apply_openrouter_tool_search(routes)

    for route in routes:
        assert route["supports_tool_search"] is True
        assert route["tool_search"]["execution"] == ["server"]
        assert route["tool_search"]["deferred_scope"] == "definition"
        assert route["tool_search"]["api_surfaces"] == ["responses", "messages"]
        assert route["tool_search"]["variants"] == ["regex"]
        assert route["tool_search"]["status"] == "beta"
    routes[0]["tool_search"]["variants"].append("test-only")
    assert routes[1]["tool_search"]["variants"] == ["regex"]


def test_deepseek_tool_search_is_model_and_api_specific(monkeypatch, tmp_path):
    updater = _load("update_deepseek")
    catalog = tmp_path / "deepseek.json"
    catalog.write_text('{"models":[]}', encoding="utf-8")
    monkeypatch.setattr(updater, "OUT", catalog)
    pricing = {
        "deepseek-flash": {
            "version": "DeepSeek V4 Flash",
            "off_peak": {},
            "cache_hit": 0.01,
            "input": 0.3,
            "output": 1.2,
            "ctx": 1_000_000,
            "max_out": 384_000,
            "supports_responses_api": True,
            "supports_anthropic_api": True,
        },
        "deepseek-v4-pro": {
            "version": "DeepSeek V4 Pro",
            "off_peak": {},
            "cache_hit": 0.01,
            "input": 1.0,
            "output": 2.0,
            "ctx": 1_000_000,
            "max_out": 384_000,
            "supports_responses_api": True,
            "supports_anthropic_api": True,
        },
    }

    by_id = {model["model_id"]: model for model in updater.build(pricing)}

    flash = by_id["deepseek-flash"]
    assert flash["supports_tool_search"] is True
    assert flash["tool_search"]["execution"] == ["client"]
    assert flash["tool_search"]["api_surfaces"] == ["responses", "messages"]
    assert by_id["deepseek-v4-pro"]["supports_tool_search"] is False
    assert "tool_search" not in by_id["deepseek-v4-pro"]


def test_google_model_limits_and_audio_modalities_follow_model_pages():
    rows = {
        model["model_id"]: model
        for model in json.loads(
            (ROOT / "src" / "llmcapa" / "data" / "google.json").read_text(
                encoding="utf-8"
            )
        )["models"]
    }
    assert rows["gemini-2.5-computer-use-preview-10-2025"]["context_window"] == 128_000
    assert rows["gemini-2.5-flash-image"]["context_window"] == 65_536
    assert rows["gemini-3.1-flash-lite-image"]["max_output_tokens"] == 4_096
    assert rows["gemini-3.1-flash-tts-preview"]["context_window"] == 8_192

    tts = rows["gemini-2.5-flash-preview-tts"]
    assert tts["input_modalities"] == ["text"]
    assert tts["output_modalities"] == ["audio"]
    assert tts["supports_audio_input"] is False
    assert tts["supports_audio_output"] is True
    assert tts["supports_function_calling"] is False
    assert tts["supports_json_mode"] is False
    assert tts["supports_realtime"] is False
    assert tts["audio"]["speech_generation"] is True
    assert tts["audio"]["speech_understanding"] is False

    live_audio = rows["gemini-2.5-flash-native-audio-preview-12-2025"]
    assert live_audio["input_modalities"] == ["text", "audio", "video"]
    assert live_audio["output_modalities"] == ["text", "audio"]
    assert live_audio["supports_realtime"] is True

    image = rows["gemini-nano-banana-2.1"]
    assert image["context_window"] == 131_072
    assert image["max_output_tokens"] == 32_768
    assert image["output_modalities"] == ["text", "image"]
