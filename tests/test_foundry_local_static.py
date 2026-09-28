"""Tests for the bundled Microsoft Foundry Local catalog."""

import llmcapa


def test_foundry_local_catalog_is_bundled_and_offline() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    assert models
    assert all(model.provider == "foundry-local" for model in models)
    assert all(
        model.extra.get("source_type") == "official_foundry_local_catalog_api"
        for model in models
    )


def test_foundry_local_aliases_and_capabilities_are_queryable() -> None:
    models = llmcapa.list_models(provider="foundry-local")
    model = next((item for item in models if item.aliases), models[0])
    resolved = llmcapa.get(model.model_id, provider="foundry_local")
    assert resolved.model_id == model.model_id
    assert resolved.extra.get("source_type") == "official_foundry_local_catalog_api"


def test_foundry_local_is_not_a_runtime_fetch_api() -> None:
    assert not hasattr(llmcapa, "fetch_foundry_local")
