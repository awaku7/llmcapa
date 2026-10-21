"""Azure Foundry is canonical; Azure OpenAI and Azure are exact aliases."""

import json

import pytest

from llmcapa import Registry


@pytest.fixture
def registry(monkeypatch):
    # Alias tests must not depend on local GitHub cache snapshots or networking.
    monkeypatch.setattr(Registry, "_load_github_catalog_caches", lambda _: None)
    monkeypatch.setattr(Registry, "_load_persistent_github_catalogs", lambda _: None)
    result = Registry()
    monkeypatch.setattr(result, "fetch_github_catalog", lambda *args, **kwargs: 0)
    return result


def test_azure_foundry_is_canonical_for_old_azure_openai_rows(registry):
    model = registry.get("gpt-5.4", provider="azure-foundry")
    assert model.provider == "azure-foundry"
    assert model.supports("tool_search") is True
    assert registry.get("gpt-5.4", provider="azure-openai") is model
    assert registry.get("gpt-5.4", provider="azure") is model
    assert "azure-openai" not in registry.providers()
    assert "azure-foundry" in registry.providers()


def test_azure_openai_alias_includes_all_foundry_models(registry):
    for provider in ("azure-openai", "azure-foundry", "azure"):
        assert registry.get("gpt-5.4-mini", provider).provider == "azure-foundry"
        assert registry.get("claude-opus-4-8", provider).provider == "azure-foundry"
    assert registry.get("gpt-5.4", provider="openai").provider == "openai"


def test_azure_aliases_have_identical_model_lists_and_search_results(registry):
    foundry = registry.list_models(provider="azure-foundry")
    assert foundry == registry.list_models(provider="azure-openai")
    assert foundry == registry.list_models(provider="azure")
    ids = {cap.model_id for cap in foundry}
    assert {"gpt-5.4", "gpt-5.4-mini", "claude-opus-4-8"} <= ids
    assert all(cap.provider == "azure-foundry" for cap in foundry)
    assert len(ids) == len(foundry)

    for provider in ("azure-openai", "azure-foundry", "azure"):
        results = registry.search("gpt-5.4", provider=provider)
        assert any(cap.model_id == "gpt-5.4" for cap in results)
        assert any(cap.model_id == "gpt-5.4-mini" for cap in results)


def test_azure_alias_keeps_other_provider_aliases_unchanged(registry):
    assert registry.get("nova-pro-v1", provider="bedrock").provider == "amazon"
    assert registry.get("gemini-2.5-flash", provider="gemini").provider == "google"
    assert registry._matching_providers("azure-foundry") >= {
        "azure-foundry",
        "azure-openai",
        "azure",
    }
    assert registry._matching_providers("azure-openai") >= {
        "azure-foundry",
        "azure-openai",
        "azure",
    }

@pytest.mark.parametrize("stored_provider", ("azure-foundry", "azure-openai"))
@pytest.mark.parametrize("storage", ("cache", "persistent"))
def test_azure_cached_catalog_reloads_legacy_provider(
    tmp_path, monkeypatch, stored_provider, storage
):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    model_id = "azure-legacy-catalog-reload-test"
    record = {
        "provider": "azure-openai",
        "model_id": model_id,
        "context_window": 4096,
        "max_output_tokens": 512,
    }
    if storage == "cache":
        catalog_dir = tmp_path / ".llmcapa" / "github_catalog_cache"
        payload = {
            "ref": "main",
            "providers": [stored_provider],
            "files": {"azure_foundry.json": json.dumps({"models": [record]})},
        }
    else:
        catalog_dir = tmp_path / ".llmcapa" / "catalogs" / "github"
        payload = {
            "source": "https://github.com/awaku7/llmcapa",
            "ref": "main",
            "providers": [stored_provider],
            "models": [record],
        }
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "azure-legacy-test.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    restarted = Registry()
    loaded = [
        cap
        for cap in restarted.list_models(provider="azure-foundry")
        if cap.model_id == model_id
    ]
    assert len(loaded) == 1
    assert loaded[0].provider == "azure-foundry"
    assert loaded[0].context_window == 4096
    for provider in ("azure-foundry", "azure-openai", "azure"):
        assert restarted.get(model_id, provider=provider) is loaded[0]
