"""Azure Foundry catalog aliases must not hide or misclassify OpenAI models."""

import pytest

from llmcapa import ModelNotFoundError, Registry


@pytest.fixture
def registry(monkeypatch):
    # A local miss must not initiate a network refresh during alias tests.
    monkeypatch.setattr(Registry, "_load_github_catalog_caches", lambda _: None)
    monkeypatch.setattr(Registry, "_load_persistent_github_catalogs", lambda _: None)
    result = Registry()
    monkeypatch.setattr(result, "fetch_github_catalog", lambda *args, **kwargs: 0)
    return result


def test_azure_foundry_alias_finds_azure_openai_models(registry):
    model = registry.get("gpt-5.4", provider="azure-foundry")
    assert model.provider == "azure-openai"
    assert model.supports("tool_search") is True
    assert registry.get("gpt-5.4", provider="azure-openai") is model


def test_azure_foundry_preserves_its_own_model_records(registry):
    model = registry.get("gpt-5.4-mini", provider="azure-foundry")
    assert model.provider == "azure-foundry"
    partner = registry.get("claude-opus-4-8", provider="azure-foundry")
    assert partner.provider == "azure-foundry"


def test_azure_openai_remains_strictly_scoped(registry):
    assert registry.get("gpt-5.4", provider="azure").provider == "azure-openai"
    with pytest.raises(ModelNotFoundError):
        registry.get("claude-opus-4-8", provider="azure-openai")


def test_azure_foundry_list_and_search_include_both_provider_records(registry):
    foundry = registry.list_models(provider="azure-foundry")
    openai = registry.list_models(provider="azure-openai")
    keys = {(cap.provider, cap.model_id) for cap in foundry}
    assert ("azure-openai", "gpt-5.4") in keys
    assert ("azure-foundry", "gpt-5.4-mini") in keys
    assert ("azure-foundry", "claude-opus-4-8") in keys
    assert all(cap.provider == "azure-openai" for cap in openai)
    assert len(keys) == len(foundry)
    found = registry.search("gpt-5.4", provider="azure-foundry")
    assert any(x.model_id == "gpt-5.4" for x in found)
    assert any(x.model_id == "gpt-5.4-mini" for x in found)


def test_azure_alias_keeps_other_provider_aliases_unchanged(registry):
    assert registry.get("nova-pro-v1", provider="bedrock").provider == "amazon"
    assert registry.get("gemini-2.5-flash", provider="gemini").provider == "google"
    assert registry._matching_providers("azure-foundry") >= {
        "azure-foundry",
        "azure-openai",
    }
