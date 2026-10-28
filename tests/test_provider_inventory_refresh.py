from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_provider_update(name: str):
    path = ROOT / "scripts" / "provider_updates" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(
        f"test_provider_inventory_{name}", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_script(name: str):
    path = ROOT / "scripts" / f"_{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_script_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_ai21_parser_extracts_current_versioned_and_alias_endpoints_only():
    updater = _load_provider_update("ai21")
    docs = """## Model Details
| Model | Model Size | Max Tokens | Version | Snapshot | API Endpoint |
| - | - | - | - | - | - |
| Jamba Large | 398B | 256K | 1.7 | 2025-07 | `jamba-large` |
| Jamba Mini | 52B | 256K | 2 | 2026-01 | `jamba-mini` |
| Jamba 3B | 3B | 256K | 2 | 2026-01 | N/A |
## API Versioning
- `jamba-large` currently points to `jamba-large-1.7-2025-07`
- `jamba-large-1.7` points to `jamba-large-1.7-2025-07`
## Model Deprecation
- `jamba-old` retired
"""
    assert updater.parse_model_ids(docs) == [
        "jamba-large",
        "jamba-large-1.7",
        "jamba-large-1.7-2025-07",
        "jamba-mini",
    ]


def test_perplexity_pricing_parser_refreshes_only_its_model_subcatalogs():
    updater = _load_provider_update("perplexity")
    docs = """export const PRICING = {
      "sonar": {"models": [{"id": "sonar", "label": "Sonar", "input": 1, "output": 2, "request": {"low": 5}},]},
      "embeddings": [{"id": "pplx-embed-context-v1-0.6b", "dims": 1024, "rate": 0.008}],
      "decisions": {"input": 0.02, "models": [{"id": "pplx-decider-v1-27b"}]},
      "agent": {"models": [{"id": "unrelated/third-party"}]}
    };
    """
    rows = updater.parse_model_inventory(docs)
    assert {row["model_id"] for row in rows} == {
        "sonar",
        "pplx-embed-context-v1-0.6b",
        "pplx-decider-v1-27b",
    }
    embedding = next(row for row in rows if row["kind"] == "embedding")
    assert embedding["dimensions"] == 1024
    assert embedding["input_per_1m"] == 0.008
    assert rows[2]["request_pricing"] == {"low": 5}


def test_perplexity_parser_reads_current_markdown_embedding_and_decision_prices():
    updater = _load_provider_update("perplexity")
    docs = r"""## Embeddings API Pricing
| Model | Dimensions | Price ($/1M tokens) |
| - | -: | -: |
| `pplx-embed-v1-0.6b` | 1024 | \$0.004 |
| `pplx-embed-context-v1-4b` | 2560 | \$0.05 |
## Decisions API Pricing
| Model | Price ($/1M input tokens) | Output tokens | Per-request fee |
| - | -: | - | - |
| `pplx-decider-v1.2` | \$0.02 | Free | None |
| `pplx-decider-flash-v1.2` | \$0.01 | Free | None |
## Cost Examples
"""
    rows = updater.parse_model_inventory(docs)
    assert [(row["model_id"], row["kind"]) for row in rows] == [
        ("pplx-decider-flash-v1.2", "decision"),
        ("pplx-decider-v1.2", "decision"),
        ("pplx-embed-context-v1-4b", "embedding"),
        ("pplx-embed-v1-0.6b", "embedding"),
    ]
    by_id = {row["model_id"]: row for row in rows}
    assert by_id["pplx-embed-context-v1-4b"]["dimensions"] == 2560
    assert by_id["pplx-embed-context-v1-4b"]["input_per_1m"] == 0.05
    assert by_id["pplx-decider-flash-v1.2"]["input_per_1m"] == 0.01


def test_zai_model_parser_reads_chat_vision_audio_and_skips_generation_products():
    updater = _load_provider_update("z-ai")
    docs = """## Models
### Latest Models
| Model | Input | Cached | Storage | Output |
| - | - | - | - | - |
| GLM-5.3 | $1.4 | $0.26 | Free | $4.4 |
### Vision Models
| Model | Input | Cached | Storage | Output |
| - | - | - | - | - |
| GLM-4.6V | $0.3 | $0.05 | Free | $0.9 |
### Image Generation Models
| Model | Price |
| GLM-Image | $0.015 |
    ### Audio Models
    | Model | Price |
    | - | - |
    | GLM-ASR-2512 | $0.03 / MTok |
"""
    rows = updater.parse_model_inventory(docs)
    assert [(row["model_id"], row["kind"]) for row in rows] == [
        ("glm-4.6v", "vision"),
        ("glm-5.3", "chat"),
        ("glm-asr-2512", "audio"),
    ]
    assert (
        next(row for row in rows if row["model_id"] == "glm-5.3")["input_per_1m"] == 1.4
    )


def test_vllm_catalog_derives_static_records_from_huggingface_metadata():
    updater = _load_script("update_local_inference_catalogs_from_hf")
    source = {
        "models": [
            {
                "provider": "huggingface",
                "model_id": "Example/Chat-Model",
                "display_name": "Example Chat Model",
                "pipeline_tag": "text-generation",
                "context_window": 8192,
                "max_output_tokens": 2048,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "supports_vision": False,
                "downloads": 1234,
                "likes": 56,
            },
            {
                "provider": "huggingface",
                "model_id": "Example/Embed-Model",
                "pipeline_tag": "feature-extraction",
                "input_modalities": ["text"],
                "output_modalities": ["embedding"],
            },
            {
                "provider": "huggingface",
                "model_id": "Qwen/Qwen3.6-35B-A3B",
                "display_name": "Qwen/Qwen3.6-35B-A3B",
                "pipeline_tag": "image-text-to-text",
                "context_window": 262144,
                "input_modalities": ["text", "image", "video"],
                "output_modalities": ["text"],
                "supports_vision": True,
            },
        ]
    }
    previous = [
        {
            "provider": "vllm",
            "model_id": "Example/Chat-Model",
            "context_window": 0,
            "max_output_tokens": 0,
            "pricing": {"input_per_1m": 0.0, "output_per_1m": 0.0},
            "extra": {
                "official_catalog_status": "legacy sample",
                "endpoints": [{"base_url": "http://localhost:8000/v1"}],
            },
        },
        {
            "provider": "vllm",
            "model_id": "Example/Legacy-Model",
            "context_window": 4096,
            "max_output_tokens": 1024,
        },
        {
            "provider": "vllm",
            "model_id": "Qwen/Qwen3.6-35B-A3B",
            "context_window": 262144,
            "max_output_tokens": 0,
            "input_modalities": ["text", "image", "video"],
            "output_modalities": ["text"],
            "aliases": ["qwen3.6"],
            "supports_function_calling": True,
            "supports_reasoning": True,
            "extra": {
                "official_vllm_recipe_url": "https://recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B",
                "vllm_min_version": "0.17.0",
                "endpoints": [{"base_url": "http://localhost:8000/v1"}],
            },
        },
    ]

    catalog = updater.build_catalog(source, previous)
    rows = {row["model_id"]: row for row in catalog["models"]}

    assert set(rows) == {
        "Example/Chat-Model",
        "Example/Embed-Model",
        "Example/Legacy-Model",
        "Qwen/Qwen3.6-35B-A3B",
    }
    current = rows["Example/Chat-Model"]
    assert current["provider"] == "vllm"
    assert current["context_window"] == 8192
    assert current["max_output_tokens"] == 0
    assert current["supports_chat_completion"] is True
    assert current["supports_streaming"] is True
    assert current["supports_responses_api"] is True
    assert current["supports_json_mode"] is True
    assert current["supports_json_schema"] is True
    assert current["pricing"] == previous[0]["pricing"]
    assert current["extra"]["metadata_source"] == "huggingface"
    assert current["extra"]["huggingface_downloads"] == 1234
    assert current["extra"]["endpoints"] == previous[0]["extra"]["endpoints"]
    assert "official_catalog_status" not in current["extra"]
    assert rows["Example/Embed-Model"]["output_modalities"] == ["embedding"]
    assert rows["Example/Embed-Model"]["supports_responses_api"] is None
    qwen = rows["Qwen/Qwen3.6-35B-A3B"]
    assert qwen["context_window"] == 262144
    assert qwen["max_output_tokens"] == 0
    assert qwen["input_modalities"] == ["text", "image", "video"]
    assert qwen["supports_vision"] is True
    assert qwen["supports_chat_completion"] is True
    assert qwen["supports_responses_api"] is True
    assert qwen["extra"]["metadata_source"] == "huggingface"
    assert qwen["extra"]["official_vllm_recipe_url"] == (
        "https://recipes.vllm.ai/Qwen/Qwen3.6-35B-A3B"
    )
    assert qwen["extra"]["vllm_min_version"] == "0.17.0"
    assert qwen["supports_function_calling"] is True
    assert qwen["supports_reasoning"] is True
    assert (
        rows["Example/Legacy-Model"]["extra"]["not_listed_in_huggingface_snapshot"]
        is True
    )


def test_huggingface_refresh_preserves_curated_unknown_fields_for_current_models():
    scraper = _load_script("scrape_huggingface")
    current = [
        {
            "provider": "huggingface",
            "model_id": "Qwen/Qwen3.6-35B-A3B",
            "context_window": 0,
            "max_output_tokens": 2048,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "aliases": ["Qwen3.6-35B-A3B"],
            "supports_function_calling": None,
            "extra": {"huggingface_tags": ["image-text-to-text"]},
        }
    ]
    previous = [
        {
            "provider": "huggingface",
            "model_id": "qwen/qwen3.6-35b-a3b",
            "context_window": 262144,
            "max_output_tokens": 0,
            "input_modalities": ["text", "image", "video"],
            "output_modalities": ["text"],
            "aliases": ["qwen3.6"],
            "license_type": "Apache-2.0",
            "supports_function_calling": False,
            "extra": {"context_window_source": "official-model-doc"},
        }
    ]

    merged = scraper.retain_unlisted_models(current, previous)
    qwen = merged[0]
    assert qwen["context_window"] == 262144
    assert qwen["max_output_tokens"] == 0
    assert qwen["input_modalities"] == ["text", "image", "video"]
    assert qwen["aliases"] == ["Qwen3.6-35B-A3B", "qwen3.6"]
    assert qwen["license_type"] == "Apache-2.0"
    assert qwen["extra"] == {
        "context_window_source": "official-model-doc",
        "huggingface_tags": ["image-text-to-text"],
    }
    assert qwen["supports_function_calling"] is None


def test_ollama_updater_overlays_responses_api_only_for_chat_models():
    updater = _load_script("update_ollama")
    chat = updater.entry(
        {"name": "qwen3-vl:8b", "details": {}},
        None,
    )
    assert chat["supports_chat_completion"] is True
    assert chat["supports_streaming"] is True
    assert chat["supports_responses_api"] is True
    assert chat["supports_json_mode"] is True
    assert chat["supports_json_schema"] is True
    assert chat["extra"]["responses_api_min_version"] == "0.13.3"
    assert chat["extra"]["responses_api_stateful"] is False

    embedding_old = {
        "provider": "ollama",
        "model_id": "embed-model",
        "input_modalities": ["text"],
        "output_modalities": ["embedding"],
        "supports_chat_completion": False,
    }
    embedding = updater.entry({"name": "embed-model", "details": {}}, embedding_old)
    assert embedding["supports_responses_api"] is False


def test_huggingface_scraper_fetches_without_a_text_only_pipeline_filter(monkeypatch):
    scraper = _load_script("scrape_huggingface")
    calls = []

    class Response:
        def __init__(self):
            self.status_code = 200
            self.headers = {}
            self.text = ""

        def json(self):
            return [
                {
                    "id": "Qwen/Qwen3.6-35B-A3B",
                    "pipeline_tag": "image-text-to-text",
                    "downloads": 10,
                }
            ]

    class Session:
        def get(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        def close(self):
            pass

    monkeypatch.setattr(scraper.requests, "Session", Session)
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)

    rows = scraper.fetch_models(min_downloads=1)

    assert rows[0]["pipeline_tag"] == "image-text-to-text"
    assert "pipeline_tag" not in calls[0][1]["params"]


def test_huggingface_scraper_collects_multiple_modalities_and_leaves_unknowns_unknown():
    scraper = _load_script("scrape_huggingface")
    rows = scraper.convert_to_catalog_format(
        [
            {
                "id": "Qwen/Qwen3.6-35B-A3B",
                "pipeline_tag": "image-text-to-text",
                "tags": ["qwen3_5_moe", "license:apache-2.0"],
                "downloads": 10000,
            },
            {"id": "org/image-gen", "pipeline_tag": "text-to-image", "tags": []},
            {
                "id": "org/asr",
                "pipeline_tag": "automatic-speech-recognition",
                "tags": [],
            },
            {"id": "org/unknown-task", "pipeline_tag": None, "tags": []},
        ]
    )
    by_id = {row["model_id"]: row for row in rows}

    qwen = by_id["Qwen/Qwen3.6-35B-A3B"]
    assert qwen["pipeline_tag"] == "image-text-to-text"
    assert qwen["input_modalities"] == ["text", "image"]
    assert qwen["output_modalities"] == ["text"]
    assert qwen["supports_vision"] is True
    assert qwen["supports_function_calling"] is None
    assert qwen["extra"]["huggingface_tags"] == ["qwen3_5_moe", "license:apache-2.0"]

    assert by_id["org/image-gen"]["input_modalities"] == ["text"]
    assert by_id["org/image-gen"]["output_modalities"] == ["image"]
    assert by_id["org/asr"]["input_modalities"] == ["audio"]
    assert by_id["org/asr"]["output_modalities"] == ["text"]
    assert by_id["org/unknown-task"]["input_modalities"] == []
    assert by_id["org/unknown-task"]["output_modalities"] == []


def test_local_runtime_catalogs_enrich_existing_ids_from_hf_without_connecting():
    updater = _load_script("update_local_inference_catalogs_from_hf")
    source = {
        "models": [
            {
                "model_id": "Org/Model-A",
                "display_name": "Model A",
                "pipeline_tag": "text-generation",
                "context_window": 8192,
                "input_modalities": ["text"],
                "output_modalities": ["text"],
                "downloads": 99,
                "likes": 3,
            },
            {
                "model_id": "Org/Model-B",
                "pipeline_tag": "text-generation",
                "context_window": 4096,
            },
            {
                "model_id": "Org/Model-Image",
                "pipeline_tag": "image-text-to-text",
                "input_modalities": ["text", "image"],
                "output_modalities": ["text"],
            },
        ]
    }
    previous = [
        {
            "provider": "runtime",
            "model_id": "Org/Model-A",
            "context_window": 0,
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "extra": {"inventory_scope": "local_installation_only"},
        },
        {
            "provider": "runtime",
            "model_id": "legacy/local-alias",
            "context_window": 4096,
            "extra": {"inventory_scope": "configured_server_only"},
        },
    ]

    for provider in ("llama-cpp", "lmstudio"):
        catalog = updater.build_catalog(source, previous, provider=provider)
        rows = {row["model_id"]: row for row in catalog["models"]}
        assert set(rows) == {
            "Org/Model-A",
            "Org/Model-B",
            "Org/Model-Image",
            "legacy/local-alias",
        }
        assert rows["Org/Model-A"]["provider"] == provider
        assert rows["Org/Model-A"]["context_window"] == 8192
        assert rows["Org/Model-A"]["extra"]["metadata_source"] == "huggingface"
        assert "inventory_scope" not in rows["Org/Model-A"]["extra"]
        assert rows["Org/Model-B"]["extra"]["metadata_source"] == "huggingface"
        assert rows["Org/Model-Image"]["input_modalities"] == ["text", "image"]
        expected_responses = True if provider == "lmstudio" else None
        assert rows["Org/Model-Image"]["supports_responses_api"] is expected_responses
        assert rows["Org/Model-A"]["supports_responses_api"] is expected_responses
        assert (
            rows["legacy/local-alias"]["extra"]["not_listed_in_huggingface_snapshot"]
            is True
        )


def test_hf_org_empty_inventory_retains_previous_rows(monkeypatch):
    updater = _load_script("update_hf_official_orgs")
    monkeypatch.setattr(updater, "_fetch_json", lambda _url: ([], None))

    assert updater.fetch_models("Mancer") == []
    previous = [{"provider": "mancer", "model_id": "Mancer/legacy"}]
    rows, retained = updater.merge_inventory(
        "mancer", "Mancer", [], previous, "2026-10-24"
    )
    assert retained == 1
    assert rows[0]["model_id"] == "Mancer/legacy"
    assert rows[0]["extra"]["official_hf_current"] is False


def test_huggingface_scraper_retains_unlisted_models_without_mutating_previous():
    scraper = _load_script("scrape_huggingface")
    previous = [
        {
            "provider": "huggingface",
            "model_id": "Qwen/Qwen-72B",
            "context_window": 32768,
            "extra": {"curated": True},
        },
        {"provider": "huggingface", "model_id": "org/current"},
    ]
    current = [{"provider": "huggingface", "model_id": "org/current"}]

    merged = scraper.retain_unlisted_models(current, previous)

    assert [row["model_id"] for row in merged] == ["org/current", "Qwen/Qwen-72B"]
    assert merged[-1]["extra"] == {
        "curated": True,
        "not_in_current_update_selection": True,
    }
    assert previous[0]["extra"] == {"curated": True}


def test_hf_inventory_follows_link_header_and_deduplicates_model_ids(monkeypatch):
    updater = _load_script("update_hf_official_orgs")
    calls = []

    def fake_fetch(url):
        calls.append(url)
        if len(calls) == 1:
            return (
                [{"modelId": "org/one"}, {"modelId": "org/two"}],
                '<https://huggingface.co/api/models?page=2>; rel="next"',
            )
        return ([{"modelId": "org/two"}, {"modelId": "org/three"}], None)

    monkeypatch.setattr(updater, "_fetch_json", fake_fetch)
    assert [row["modelId"] for row in updater.fetch_models("org")] == [
        "org/one",
        "org/three",
        "org/two",
    ]
    assert len(calls) == 2


def test_hf_inventory_merge_preserves_curated_rows_and_marks_removed_rows():
    updater = _load_script("update_hf_official_orgs")
    previous = [
        {
            "provider": "sample",
            "model_id": "org/kept",
            "context_window": 64000,
            "extra": {"hand_checked": True},
        },
        {"provider": "sample", "model_id": "org/removed", "context_window": 32000},
    ]
    records = [
        {
            "modelId": "org/kept",
            "pipeline_tag": "text-generation",
            "tags": ["text-generation"],
        },
        {
            "modelId": "org/new",
            "pipeline_tag": "image-text-to-text",
            "tags": ["vision"],
        },
    ]
    result, retained = updater.merge_inventory(
        "sample", "org", records, previous, "2026-10-12"
    )
    assert retained == 1
    assert result[0]["context_window"] == 64000
    assert result[0]["extra"]["hand_checked"] is True
    assert result[1]["input_modalities"] == ["text", "image"]
    assert result[1]["output_modalities"] == ["text"]
    assert result[-1]["extra"]["official_hf_current"] is False


def test_morph_inventory_parser_reads_native_specs_and_ignores_openrouter_mapping():
    updater = _load_provider_update("morph")
    payload = {
        "data": [
            {
                "id": "morph-kimi-test",
                "name": "Morph Kimi Test",
                "description": "provider model",
                "openrouter": {"slug": "do-not-copy/this"},
                "input_modalities": [
                    {
                        "type": "text",
                        "supported_inputs": {
                            "max_context_length": {"value": 128000, "unit": "token"}
                        },
                        "pricing": [{"type": "prompt", "cost_usd": "0.000001"}],
                    },
                    {"type": "image"},
                ],
                "output_modalities": [
                    {
                        "type": "text",
                        "max_length": {"value": 16000, "unit": "token"},
                        "streaming": True,
                        "supported_parameters": {
                            "tools": {"type": "boolean"},
                            "json_mode": {"type": "boolean"},
                            "structured_outputs": {"type": "boolean"},
                        },
                        "pricing": [{"type": "completion", "cost_usd": "0.000002"}],
                    }
                ],
                "is_ready": True,
            }
        ]
    }
    [row] = updater.parse_inventory(payload, checked_at="2026-10-12")
    assert row["model_id"] == "morph-kimi-test"
    assert row["context_window"] == 128000
    assert row["input_modalities"] == ["image", "text"]
    assert row["pricing"] == {
        "input_per_1m": 1.0,
        "output_per_1m": 2.0,
        "currency": "USD",
    }
    assert row["supports_function_calling"] is True
    assert "openrouter" not in row["extra"]
    assert "do-not-copy" not in str(row)


def test_morph_inventory_refuses_empty_api_result():
    updater = _load_provider_update("morph")
    import pytest

    with pytest.raises(ValueError, match="no usable model IDs"):
        updater.parse_inventory({"data": []})


def test_bytedance_seed_scraper_reads_only_official_seed_and_seedream_tables():
    updater = _load_provider_update("bytedance-seed")
    page = """<h1>模型列表</h1><table>
    <tr><td>doubao-seed-2-1-pro-260915</td><td>上下文窗口: 1024k 最大回答(默认 4k): 256k 多模态理解 工具调用 结构化输出 深度思考</td></tr>
    <tr><td>doubao-seed-2-0-pro-260215 即将下线</td><td>上下文窗口: 256k 最大回答(默认 4k): 128k</td></tr>
    <tr><td>doubao-seedream-5-0-pro-260628</td><td>文生图 多参考图生图</td></tr>
    <tr><td>doubao-seedance-2-5-260628</td><td>图生视频 参考图</td></tr>
    <tr><td>deepseek-v4-pro-ga-260813</td><td>text</td></tr>
    </table>"""
    rows = updater.parse_model_inventory(page)
    assert [row["model_id"] for row in rows] == [
        "doubao-seed-2-0-pro-260215",
        "doubao-seed-2-1-pro-260915",
        "doubao-seedance-2-5-260628",
        "doubao-seedream-5-0-pro-260628",
    ]
    current = rows[1]
    assert current["context_window"] == 1_024_000
    assert current["max_output_tokens"] == 256_000
    assert current["supports_function_calling"] is True
    assert next(row for row in rows if row["kind"] == "image")["input_modalities"] == [
        "text",
        "image",
    ]
    video = next(row for row in rows if row["kind"] == "video")
    assert video["input_modalities"] == ["text", "image"]
    assert video["output_modalities"] == ["video"]
    assert rows[0]["deprecated"] is True


def test_poolside_scraper_extracts_supported_models_and_context_from_docs():
    updater = _load_provider_update("poolside")
    docs = {
        "models": """## Compare models
| Detail | [](https://docs.poolside.ai/release-notes/models.md#laguna-s-2-1) | [](https://docs.poolside.ai/release-notes/models.md#laguna-xs-2-1) | [](https://docs.poolside.ai/release-notes/models.md#laguna-m-1) |
| - | - | - | - |
| Model | [Laguna S 2.1](https://docs.poolside.ai/release-notes/models.md#laguna-s-2-1) | [Laguna XS 2.1](https://docs.poolside.ai/release-notes/models.md#laguna-xs-2-1) | [Laguna M.1](https://docs.poolside.ai/release-notes/models.md#laguna-m-1) |
| Context window | 1M tokens | 256K tokens | 256K tokens |
""",
        "api": "Use `poolside/laguna-s-2.1` for hosted inference.",
    }
    rows = updater.parse_model_inventory(docs)
    assert [row["model_id"] for row in rows] == [
        "laguna-m-1",
        "laguna-s-2.1",
        "laguna-xs-2.1",
    ]
    assert (
        next(row for row in rows if row["model_id"] == "laguna-s-2.1")["context_window"]
        == 1_000_000
    )


def test_relace_scraper_parses_public_model_table_and_product_model_ids():
    updater = _load_provider_update("relace")
    docs = {
        "open_models": """| Model | Slug | Context | Input | Output | Cached Input |
| - | - | - | - | - | - |
| DeepSeek Flash | `deepseek-ai/DeepSeek-V4-Flash-0731` | 1M | $0.065 / M | $0.18 / M | $0.016 / M |
| Kimi K3 | `moonshotai/kimi-k3` | 1M | $3.00 / M | $15.00 / M | $0.30 / M |
""",
        "apply": "The current apply model is `relace-apply-3`.",
        "search": "Run the Fast Agentic Search model (`relace-search`).",
    }
    rows = updater.parse_model_inventory(docs)
    assert {row["model_id"] for row in rows} == {
        "deepseek-ai/DeepSeek-V4-Flash-0731",
        "moonshotai/kimi-k3",
        "relace-apply-3",
        "relace-search",
    }
    deepseek = next(row for row in rows if row["model_id"].startswith("deepseek-ai/"))
    assert deepseek["context_window"] == 1_000_000
    assert deepseek["pricing"]["input_per_1m"] == 0.065


def test_sakana_scraper_reads_public_model_parameters_without_api_credentials():
    updater = _load_provider_update("sakana")
    docs = {
        "get_started": 'Use model="fugu" and model="fugu-ultra-v1.1". Also model="fugu-cyber".',
        "models": "The public models include Fugu Max and `fugu-max`; Fugu Ultra version `fugu-ultra-v2.0`.",
        "pricing": "Fixed pricing for fugu-max-v1.0. The model `sakana-namazu-v1.0` is separately billed.",
    }
    rows = updater.parse_model_inventory(docs)
    assert {row["model_id"] for row in rows} >= {
        "fugu",
        "fugu-ultra-v1.1",
        "fugu-ultra-v2.0",
        "fugu-max",
        "fugu-max-v1.0",
        "fugu-cyber",
        "sakana-namazu",
        "sakana-namazu-v1.0",
    }


def test_writer_scraper_reads_public_palmyra_ids_specs_and_prices():
    updater = _load_provider_update("writer")
    docs = {
        "models": """## Model comparison
| Feature | Palmyra X6 | Palmyra X5 | Palmyra X4 |
| - | - | - | - |
| **API model ID** | `palmyra-x6` | `palmyra-x5` | `palmyra-x4` |
| **Context window** | 1M tokens | 1M tokens | 128k tokens |
| **Max output** | 8,192 tokens | 8,192 tokens | 4,096 tokens |
Deprecation notice: Palmyra X4 and X5 will be deprecated on **2099-12-14**.
""",
        "pricing": """## Base model
| Model name | Model ID | Input / 1M | Output / 1M |
| - | - | - | - |
| Palmyra X6 | `palmyra-x6` | $2.00 | $8.00 |
| Palmyra X5 | `palmyra-x5` | $0.60 | $6.00 |
| Palmyra X4 | `palmyra-x4` | $2.50 | $10.00 |
""",
    }
    rows = updater.parse_model_inventory(docs)
    assert {row["model_id"] for row in rows} == {
        "palmyra-x6",
        "palmyra-x5",
        "palmyra-x4",
    }
    x6 = next(row for row in rows if row["model_id"] == "palmyra-x6")
    assert x6["context_window"] == 1_000_000
    assert x6["input_per_1m"] == 2.0
    assert x6["output_per_1m"] == 8.0


def test_lmstudio_parser_accepts_local_hub_model_keys():
    updater = _load_provider_update("lmstudio")
    rows = updater.parse_model_inventory(
        [
            {
                "key": "publisher/model-quantized",
                "display_name": "Model Quantized",
                "type": "llm",
                "max_context_length": 65536,
            },
            {"id": "publisher/embed", "type": "embedding"},
        ]
    )
    assert [row["model_id"] for row in rows] == [
        "publisher/model-quantized",
        "publisher/embed",
    ]
    assert rows[0]["context_length"] == 65536


def test_llama_cpp_parser_reads_only_models_exposed_by_running_server():
    updater = _load_provider_update("llama_cpp")
    assert updater.parse_model_inventory(
        [{"id": "active-local-model", "created": 42}]
    ) == [
        {
            "model_id": "active-local-model",
            "display_name": "active-local-model",
            "created": 42,
        }
    ]


def test_tinker_parser_uses_exact_tinker_ids_and_reads_context_and_price():
    updater = _load_provider_update("thinkingmachines")
    docs = """## Training
| Model | Context | Size | Active | Arch | Type | Tinker ID | Prefill | Sample | Train |
| - | - | - | - | - | - | - | - | - | - |
| [Inkling](https://huggingface.co/thinkingmachines/Inkling) | 64K | 975B | 41B | MoE | Hybrid + Audio + Vision | thinkingmachines/Inkling | ~~$3.74~~ $1.87, $0.374 (cached) | ~~$9.36~~ $4.68 | $5.61 |
| [Qwen 3](https://huggingface.co/Qwen/Qwen3) | 128K | 8B | 8B | Dense | Hybrid | Qwen/Qwen3-8B:peft:131072 | $0.195, $0.039 (cached) | $0.60 | $0.44 |
## Serverless Inference (Beta)
| Model | Tinker ID | Context | Prefill (Input) | Sample (Output) |
| - | - | - | - | - |
| Inkling | thinkingmachines/Inkling | 64K | $1.87 | $4.68 |
"""
    rows = updater.parse_model_inventory(docs)
    assert {row["model_id"] for row in rows} == {
        "thinkingmachines/Inkling",
        "Qwen/Qwen3-8B:peft:131072",
    }
    inkling = next(row for row in rows if row["model_id"] == "thinkingmachines/Inkling")
    assert inkling["context_window"] == 64000
    assert inkling["input_per_1m"] == 1.87
    assert inkling["output_per_1m"] == 4.68
    assert "vision" in inkling["model_type"].casefold()


def test_previously_authenticated_provider_updaters_now_fetch_public_docs_without_keys():
    for name in ("bytedance-seed", "poolside", "relace", "sakana", "writer"):
        updater = _load_provider_update(name)
        assert not inspect.signature(updater.fetch_inventory).parameters
        source = inspect.getsource(updater.fetch_inventory)
        assert "API_KEY" not in source
        assert "Authorization" not in source
