"""Coverage for recently added inference-provider catalogs and updaters."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import _update_baseten  # noqa: E402
import _update_deepinfra  # noqa: E402
import _update_nebius  # noqa: E402

import llmcapa  # noqa: E402


def test_new_provider_catalogs_are_registered_and_resolvable() -> None:
    providers = llmcapa.providers()
    for provider in ("baseten", "deepinfra", "nebius"):
        assert provider in providers
        models = llmcapa.list_models(provider=provider)
        assert models
        assert all(model.provider == provider for model in models)
        assert llmcapa.get(models[0].model_id, provider=provider) == models[0]

    baseten = llmcapa.get("deepseek-ai/DeepSeek-V4.1-Flash", provider="baseten")
    assert baseten.context_window == 1_048_000
    assert baseten.supports("vision") is True

    deepinfra_audio = llmcapa.get("google/gemini-2.5-flash", provider="deepinfra")
    assert deepinfra_audio.supports("audio_input") is True


def test_nebius_parser_maps_official_context_pricing_and_features() -> None:
    rows = [
        {
            "type": "image2text",
            "name": "Example Vision Model",
            "vendor": "Example",
            "status": "active",
            "use_cases": [
                "text",
                "image",
                "reasoning",
                "function_calling",
                "responses_api",
            ],
            "tags": ["JSON mode"],
            "flavors": [
                {
                    "model_id": "example/vision-model",
                    "model_name": "Example Vision Model",
                    "max_model_len": 131072,
                    "input_price_per_million_tokens": 0.5,
                    "output_price_per_million_tokens": 1.25,
                    "regions": [{"name": "eu-north1"}],
                    "external_provider": False,
                }
            ],
        }
    ]
    [model] = _update_nebius.catalog_to_models(rows)
    assert model["model_id"] == "example/vision-model"
    assert model["context_window"] == 131072
    assert model["input_modalities"] == ["text", "image"]
    assert model["supports_vision"] is True
    assert model["supports_function_calling"] is True
    assert model["supports_json_mode"] is True
    assert model["supports_responses_api"] is True
    assert model["pricing"]["input_per_1m"] == 0.5


def test_deepinfra_parser_converts_prices_and_skips_non_llm_models() -> None:
    record = {
        "model_name": "Qwen/Qwen-test-model",
        "type": "text-generation",
        "reported_type": "text-generation",
        "description": "Vision model with reasoning and tools.",
        "tags": ["openai", "multimodal", "input-audio", "reasoning", "tools", "json"],
        "pricing": {
            "type": "tokens",
            "cents_per_input_token": 0.000009,
            "cents_per_output_token": 0.000034,
        },
        "max_tokens": 131072,
        "private": 0,
    }
    parsed = _update_deepinfra.model_to_entry(record)
    assert parsed is not None
    assert parsed["context_window"] == 131072
    assert parsed["pricing"]["input_per_1m"] == 0.09
    assert parsed["pricing"]["output_per_1m"] == 0.34
    assert parsed["supports_vision"] is True
    assert parsed["input_modalities"] == ["text", "image", "audio"]
    assert parsed["supports_function_calling"] is True
    assert parsed["supports_reasoning"] is True
    assert parsed["supports_json_mode"] is True

    assert _update_deepinfra.model_to_entry({**record, "type": "text-to-video"}) is None
    assert _update_deepinfra.model_to_entry({**record, "private": 1}) is None


def _baseten_public_docs_fixture() -> str:
    return """
export const FeatureSupportTable = () => {
  const rows = [{model: "Example Vision", reasoning: "Enabled by default", vision: "✓", sampling: "temperature, stop"}];
};
export const SupportedModelsTable = () => {
  const rows = [{model: "Example Vision", slug: "example/vision-model", context: 65, maxOutput: 2}];
};
"""


def test_baseten_parser_scrapes_public_model_and_feature_tables() -> None:
    rows = _update_baseten.parse_model_inventory(_baseten_public_docs_fixture())
    [model] = _update_baseten.catalog_to_models(rows)
    assert model["model_id"] == "example/vision-model"
    assert model["context_window"] == 65_000
    assert model["max_output_tokens"] == 2_000
    assert model["supports_vision"] is True
    assert model["supports_function_calling"] is True
    assert model["supports_reasoning"] is True


def test_baseten_rendered_doc_tables_normalize_to_the_catalog_parser():
    source = _update_baseten._rendered_tables_as_source(
        [
            [
                ["Model", "Slug", "Context", "Max output"],
                ["Example Vision", "example/vision-model", "1048k", "262k"],
            ],
            [
                ["Model", "Reasoning", "Vision", "Sampling parameters"],
                ["Example Vision", "Enabled by default", "✓", "temperature, stop"],
            ],
        ]
    )
    [model] = _update_baseten.parse_model_inventory(source)

    assert model["model_id"] == "example/vision-model"
    assert model["context_window"] == 1_048_000
    assert model["max_output_tokens"] == 262_000
    assert model["supports_vision"] is True
    assert model["supports_reasoning"] is True


def test_baseten_refresh_scrapes_public_docs_without_api_key(
    tmp_path, monkeypatch, capsys
) -> None:
    destination = tmp_path / "baseten.json"
    destination.write_text('{"models": []}' + chr(10), encoding="utf-8")
    monkeypatch.setattr(_update_baseten, "DATA", destination)
    monkeypatch.setattr(_update_baseten, "fetch_docs", _baseten_public_docs_fixture)
    monkeypatch.delenv("BASETEN_API_KEY", raising=False)

    _update_baseten.main()

    saved = json.loads(destination.read_text(encoding="utf-8"))
    assert [model["model_id"] for model in saved["models"]] == ["example/vision-model"]
    assert "1 public models scraped" in capsys.readouterr().out.lower()
    assert not (tmp_path / "provider_update_log.md").exists()
