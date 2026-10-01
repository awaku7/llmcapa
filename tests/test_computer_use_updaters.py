from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS = str(Path(__file__).resolve().parents[1] / "scripts")


def _script_module(name: str):
    sys.path.insert(0, SCRIPTS)
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(SCRIPTS)


def test_google_computer_use_metadata_uses_current_official_list():
    metadata = _script_module("_computer_use_metadata")
    supported = metadata.google_computer_use_capability("gemini-3.8-flash")
    assert supported is not None
    assert supported["provider"] == "google"
    assert supported["api_type"] == "generate_content"
    assert supported["tool_type"] == "computer_use"
    assert supported["status"] == "preview"
    assert supported["source_url"].endswith("/generate-content/computer-use")

    assert metadata.google_computer_use_capability("gemini-3.6-flash") is None
    assert metadata.google_computer_use_capability(
        "gemini-2.5-computer-use-preview-10-2025"
    ) is None


def test_google_shutdown_and_stale_computer_use_reconcile():
    updater = _script_module("_update_google")
    stale_source = "https://ai.google.dev/gemini-api/docs/generate-content/computer-use"
    models = [
        {"model_id": "gemini-3.8-flash"},
        {
            "model_id": "gemini-3.6-flash",
            "computer_use": {"supported": True, "source_url": stale_source},
        },
        {
            "model_id": "gemini-2.5-computer-use-preview-10-2025",
            "deprecated": False,
            "computer_use": {"supported": True},
        },
    ]

    updater.reconcile_computer_use(models)

    assert models[0]["computer_use"]["supported"] is True
    assert "computer_use" not in models[1]
    assert models[2]["deprecated"] is True
    assert "computer_use" not in models[2]
    assert models[2]["extra"]["computer_use_shutdown_date"] == "2026-07-28"


def test_meta_muse_spark_native_computer_use_is_version_scoped():
    metadata = _script_module("_computer_use_metadata")
    current = metadata.meta_computer_use_capability("muse-spark-1.3")
    assert current is not None
    assert current["provider"] == "meta"
    assert current["api_type"] == "responses"
    assert current["tool_type"] == "computer"
    assert current["status"] == "documented"
    assert current["source_url"] == "https://dev.meta.ai/docs/computer-use"
    original = metadata.meta_computer_use_capability("muse-spark-1.1")
    assert original is not None
    assert original["source_url"].endswith("introducing-muse-spark-meta-model-api/")
    assert metadata.meta_computer_use_capability("muse-spark-1.2") is None
    assert metadata.meta_computer_use_capability("muse-spark-1.3-contributor") is None

    updater = _script_module("_update_meta")
    standard = updater.spark_row(
        model_id="muse-spark-1.3",
        display="Meta: Muse Spark 1.3",
        tier="standard",
        table={"context": 1_048_576},
    )
    assert standard["computer_use"] == current
    contributor = updater.spark_row(
        model_id="muse-spark-1.3-contributor",
        display="Meta: Muse Spark 1.3 Contributor",
        tier="contributor",
        table={"context": 1_048_576},
    )
    assert "computer_use" not in contributor


def test_openai_model_index_deprecation_is_detected():
    updater = _script_module("_update_openai")
    paths, deprecated = updater.parse_model_index(
        "- [gpt-5.4](/api/docs/models/gpt-5.4.md): Current model.\n"
        "- [computer-use-preview](/api/docs/models/computer-use-preview.md): "
        "Deprecated. Specialized model for computer use.\n"
    )
    assert paths == [
        "/api/docs/models/gpt-5.4.md",
        "/api/docs/models/computer-use-preview.md",
    ]
    assert deprecated == {"/api/docs/models/computer-use-preview.md"}


def test_anthropic_tool_versions_are_platform_specific():
    metadata = _script_module("_computer_use_metadata")
    current = metadata.anthropic_computer_use_capability(
        "claude-opus-5-5", "anthropic"
    )
    assert current is not None
    assert current["tool_type"] == "computer_toolset_20260801"
    assert current["status"] == "ga"
    assert current["requires_beta"] is False

    older = metadata.anthropic_computer_use_capability(
        "claude-opus-4-7", "anthropic"
    )
    assert older is not None
    assert older["tool_type"] == "computer_20251124"
    assert older["beta_header"] == "computer-use-2025-11-24"

    sonnet = metadata.anthropic_computer_use_capability(
        "claude-sonnet-4-5", "anthropic"
    )
    assert sonnet is not None
    assert sonnet["tool_type"] == "computer_20250124"
    assert sonnet["beta_header"] == "computer-use-2025-01-24"

    bedrock = metadata.anthropic_computer_use_capability(
        "anthropic.claude-opus-4-7", "amazon"
    )
    assert bedrock is not None
    assert bedrock["provider"] == "amazon"
    assert bedrock["api_type"] == "bedrock-runtime"
    assert bedrock["beta_header"] == "computer-use-2025-11-24"

    assert (
        metadata.anthropic_computer_use_capability(
            "claude-opus-5-5", "azure-foundry"
        )
        is None
    )
    assert metadata.anthropic_computer_use_capability(
        "claude-opus-4-2", "anthropic"
    ) is None


def test_openrouter_refresh_preserves_only_existing_curated_computer_use():
    updater = _script_module("update_catalog_from_openrouter")
    capability = {
        "supported": True,
        "native": False,
        "api_type": "custom_harness",
        "tool_type": "custom_computer_harness",
    }
    entry = {"model_id": "anthropic/claude-opus-4.5"}
    updater.preserve_curated_computer_use(
        entry, {"computer_use": capability}
    )
    assert entry["computer_use"] == capability

    new_entry = {"model_id": "anthropic/claude-opus-4.5"}
    updater.preserve_curated_computer_use(new_entry, None)
    assert "computer_use" not in new_entry


def test_azure_foundry_builder_preserves_and_detects_computer_use(monkeypatch):
    updater = _script_module("_update_azure_foundry")
    capability = {"supported": True, "provider": "custom-harness"}
    monkeypatch.setattr(
        updater, "_PREV_LIMITS", {"kept-model": {"computer_use": capability}}
    )
    kept = updater.build_entry({"name": "kept-model"}, {})
    assert kept["computer_use"] == capability

    preview = updater.build_entry(
        {
            "name": "computer-use-preview",
            "systemCatalogData": {"publisher": "openai"},
        },
        {},
    )
    assert preview["computer_use"]["supported"] is True
    assert preview["computer_use"]["provider"] == "azure-openai"
    assert preview["computer_use"]["tool_version"] == "2025-03-11"

    gpt = updater.build_entry(
        {"name": "gpt-5.4", "entityResourceName": "azure-foundry"}, {}
    )
    assert gpt["computer_use"]["supported"] is True
    assert gpt["supports_responses_api"] is True
    assert gpt["computer_use"]["tool_type"] == "computer"

    claude = updater.build_entry(
        {"name": "claude-opus-4-7", "entityResourceName": "azure-foundry"},
        {},
    )
    assert claude["computer_use"]["tool_type"] == "computer_20251124"
    assert claude["computer_use"]["beta_header"] == "computer-use-2025-11-24"

    fireworks = updater.build_entry(
        {"name": "FW-GLM-5", "entityResourceName": "azure-foundry"}, {}
    )
    assert fireworks["provider"] == "fireworks"
    assert fireworks["supports_function_calling"] is True
    assert fireworks["supports_streaming"] is True
    assert fireworks["azure_lifecycle"] == "GA"
    assert fireworks["license_type"] == "custom"
    assert fireworks["extra"]["capabilities_source"].endswith("/FW-GLM-5")

    rows = [
        {"provider": "azure-foundry", "model_id": "claude-sonnet-5"},
        {"provider": "azure-foundry", "model_id": "claude-opus-5-5"},
    ]
    updater.reconcile_computer_use(rows)
    assert rows[0]["computer_use"]["tool_type"] == "computer_20251124"
    assert "computer_use" not in rows[1]


def test_amazon_updater_can_reconcile_bedrock_models_without_optional_scraper(
    monkeypatch, tmp_path
):
    updater = _script_module("_update_amazon")
    source = tmp_path / "anthropic.json"
    source.write_text(
        '{"models":[{"model_id":"claude-opus-5-5",'
        '"display_name":"Claude Opus 5.5","context_window":1000000,'
        '"max_output_tokens":128000,"input_modalities":["text","image"],'
        '"output_modalities":["text"],"supports_vision":true,'
        '"supports_function_calling":true,"supports_reasoning":true}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "ANTHROPIC_DATA", source)
    models = []
    inserted = updater.add_bedrock_claude_models(models)
    assert inserted == 1
    assert models[0]["model_id"] == "anthropic.claude-opus-5-5"
    assert models[0]["computer_use"]["tool_type"] == "computer_20251124"

    catalog = tmp_path / "amazon.json"
    catalog.write_text(
        '{"models":[{"model_id":"nova-pro-v1","pricing":'
        '{"input_per_1m":0.8,"output_per_1m":3.2}}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "OUT", catalog)
    monkeypatch.setattr(updater, "_fetch_nova_prices", None)
    assert updater.fetch_nova_prices() == {
        "nova-pro-v1": {"input": 0.8, "output": 3.2}
    }
    assert updater.NOVA_PRICING_MODE == "bundled-cache"


def test_openrouter_live_refresh_preserves_curated_metadata_but_uses_live_fields():
    updater = _script_module("_update_openrouter")
    previous = {
        "model_id": "unbiased/pareto",
        "supports_json_mode": False,
        "extra": {"cache_read_per_1m": 0.5, "curated_note": "retain me"},
        "document": {"accepts_file": True},
    }
    live = {
        "model_id": "unbiased/pareto",
        "supports_json_mode": True,
        "pricing": {"input_per_1m": 1.0},
        "extra": {"source": "live", "supported_parameters": ["response_format"]},
    }

    merged = updater.preserve_openrouter_metadata(live, previous)

    assert merged["supports_json_mode"] is True
    assert merged["pricing"]["input_per_1m"] == 1.0
    assert merged["document"] == {"accepts_file": True}
    assert merged["extra"]["curated_note"] == "retain me"
    assert "cache_read_per_1m" not in merged["extra"]
    assert merged["extra"]["supported_parameters"] == ["response_format"]


def test_vertex_updater_refuses_to_overwrite_with_empty_sdk_result(monkeypatch):
    updater = _script_module("_update_vertex_ai")
    monkeypatch.setattr(updater, "discover_models", list)
    with pytest.raises(RuntimeError, match="refusing to overwrite catalog"):
        updater.main()


def test_reconciled_catalog_reports_provider_specific_computer_use(monkeypatch):
    import llmcapa

    # User-owned GitHub cache snapshots override bundled data; isolate this
    # test from cache state on the developer's machine.
    monkeypatch.setattr(llmcapa.Registry, "_load_github_catalog_caches", lambda _: None)
    monkeypatch.setattr(llmcapa.Registry, "_load_persistent_github_catalogs", lambda _: None)
    registry = llmcapa.Registry()
    for model_id, provider in (
        ("gpt-5.4", "openai"),
        ("claude-opus-5-5", "anthropic"),
        ("anthropic.claude-opus-5-5", "amazon"),
        ("gemini-3.8-flash", "google"),
        ("gemini-3.8-flash", "vertex-ai"),
        ("computer-use-preview", "azure-openai"),
        ("gpt-5.4", "azure-foundry"),
        ("qwen3-vl:8b", "ollama"),
        ("muse-spark-1.1", "meta"),
        ("muse-spark-1.3", "meta"),
    ):
        assert registry.get(model_id, provider).supports("computer_use") is True

    retired = registry.get("gemini-2.5-computer-use-preview-10-2025", "google")
    assert retired.supports("computer_use") is False
    assert retired.deprecated is True
    assert registry.get("computer-use-preview", "openai").deprecated is True
    assert registry.get("qwen3-vl:8b", "ollama").computer_use.native is False
