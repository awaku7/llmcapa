"""Tests for llmcapa registry and data files."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llmcapa
from llmcapa import Capability, ModelNotFoundError
from llmcapa.registry import Registry

DATA_DIR = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"

REQUIRED_KEYS = {"provider", "model_id", "context_window", "max_output_tokens"}


def _all_records():
    for path in sorted(DATA_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload["models"]:
            yield path.name, record


# ----------------------------------------------------------------------
# data schema
# ----------------------------------------------------------------------
def test_data_files_exist():
    assert list(DATA_DIR.glob("*.json")), "no bundled data files"


@pytest.mark.parametrize("fname,record", list(_all_records()))
def test_record_schema(fname, record):
    missing = REQUIRED_KEYS - set(record)
    assert not missing, f"{fname}: {record.get('model_id')}: missing {missing}"
    assert isinstance(record["context_window"], int) and record["context_window"] > 0
    # Some bundled records may have max_output_tokens=0 when the provider
    # does not publish a reliable limit.
    assert isinstance(record["max_output_tokens"], int) and record["max_output_tokens"] >= 0
    # must round-trip through Capability
    cap = Capability.from_dict(record)
    assert cap.model_id == record["model_id"]


def test_no_duplicate_model_ids():
    seen = {}
    for fname, record in _all_records():
        mid = record["model_id"].lower()
        # Aggregator/reseller files (novita, openrouter) may intentionally
        # overlap with native provider data; the registry uses
        # first-registered-wins for unqualified lookups.
        if fname in ("novita.json", "openrouter.json", "azure_foundry.json", "lmstudio.json", "ollama.json"):
            continue
        assert mid not in seen, f"duplicate model_id {mid} in {fname} and {seen[mid]}"
        seen[mid] = fname


# ----------------------------------------------------------------------
# lookup
# ----------------------------------------------------------------------
def test_get_by_id():
    cap = llmcapa.get("gpt-4o")
    assert cap.provider == "openai"
    assert cap.context_window == 128000


def test_get_by_alias():
    cap = llmcapa.get("gpt-4o-2024-08-06")
    assert cap.model_id == "gpt-4o"


def test_get_unknown():
    with pytest.raises(ModelNotFoundError):
        llmcapa.get("this-model-does-not-exist")


def test_providers():
    p = llmcapa.providers()
    assert isinstance(p, list)
    assert len(p) > 10
    assert "openai" in p
    assert "novita" in p


def test_list_all():
    models = llmcapa.list_models()
    assert len(models) > 100


def test_list_by_provider():
    models = llmcapa.list_models(provider="openai")
    assert all(c.provider.lower() == "openai" for c in models)
    assert len(models) > 10


def test_list_novita():
    models = llmcapa.list_models(provider="novita")
    assert all(c.provider.lower() == "novita" for c in models)
    assert len(models) >= 100


def test_find():
    results = llmcapa.find(supports_vision=True, min_context_window=100000)
    assert len(results) > 0
    for r in results:
        assert r.context_window >= 100000
        assert r.supports("vision")


def test_search():
    results = llmcapa.search("gpt-4o", provider="openai")
    assert len(results) > 0
    assert any("gpt-4o" in r.model_id for r in results)


def test_search_novita():
    results = llmcapa.search("novita", provider="novita")
    assert len(results) > 0


def test_register_and_get():
    from llmcapa import Capability

    cap = Capability(
        provider="test",
        model_id="test-model",
        context_window=1024,
        max_output_tokens=512,
    )
    llmcapa.register(cap)
    retrieved = llmcapa.get("test-model")
    assert retrieved.context_window == 1024


# ----------------------------------------------------------------------
# provider-scoped get()
# ----------------------------------------------------------------------
def test_get_with_provider():
    """get(model_id, provider=...) should return the provider-specific version."""
    cap = llmcapa.get("deepseek/deepseek-v3.2-exp", provider="novita")
    assert cap.provider == "novita"
    assert cap.context_window == 163840


def test_get_without_provider_returns_first():
    """get(model_id) without provider should return the first-registered version."""
    cap = llmcapa.get("deepseek/deepseek-v3.2")
    # native deepseek file should win over novita for unqualified lookup
    assert cap.provider in ("deepseek", "openrouter")


def test_get_with_provider_alias() -> None:
    """get(model_id, provider='bedrock') should resolve to amazon provider."""
    cap = llmcapa.get("nova-pro-v1", provider="bedrock")
    assert cap.provider == "amazon"
    assert cap.context_window == 300000


def test_get_with_provider_normalization() -> None:
    """get with azure_openai (underscore) should normalize to azure-openai."""
    cap = llmcapa.get("gpt-4o", provider="azure_openai")
    assert cap.provider == "azure-openai"
    assert cap.context_window == 128000


def test_find_model_across_providers() -> None:
    """find_model returns all (provider, Capability) tuples for a model_id."""
    results = llmcapa.find_model("gpt-4o")
    assert len(results) >= 1
    providers_found = {p for p, _ in results}
    assert "openai" in providers_found
    assert all(c.model_id.lower() == "gpt-4o" for _, c in results)


def test_list_models_with_alias() -> None:
    """list_models(provider='bedrock') should include amazon models."""
    models = llmcapa.list_models(provider="bedrock")
    assert all(c.provider == "amazon" for c in models)
    assert len(models) > 0


def test_load_extra_json(tmp_path) -> None:
    """load_extra should register models from an external JSON file."""
    extra_json = tmp_path / "extra_models.json"
    extra_json.write_text(
        '{"models": [{"provider": "custom", "model_id": "my-model", '
        '"context_window": 8192, "max_output_tokens": 2048}]}',
        encoding="utf-8",
    )
    count = llmcapa.load_extra(str(extra_json))
    assert count == 1
    cap = llmcapa.get("my-model")
    assert cap.provider == "custom"
    assert cap.context_window == 8192


def test_find_by_model_id_from_registry() -> None:
    """Registry.find_by_model_id returns results from multiple providers."""
    reg = Registry()
    reg._ensure_loaded()
    results = reg.find_by_model_id("gpt-4o")
    assert len(results) >= 1
    # spot check: at least one result has provider=openai
    assert any(p == "openai" for p, _ in results)


def test_new_providers_registered() -> None:
    """sakura and huggingface providers are loaded from bundled JSON files."""
    p = llmcapa.providers()
    assert "sakura" in p, "sakura.json was not loaded into providers()"
    assert "huggingface" in p, "huggingface.json was not loaded into providers()"


def test_new_provider_models_accessible() -> None:
    """Models from new JSON files are accessible via get()."""
    sakura = llmcapa.get("sakura-default")
    assert sakura.provider == "sakura"
    assert sakura.context_window == 4096

    hf = llmcapa.get("huggingface-default")
    assert hf.provider == "huggingface"
    assert hf.context_window == 4096


def test_provider_alias_hf_resolves_to_huggingface() -> None:
    """provider='hf' should resolve to huggingface via alias."""
    cap = llmcapa.get("huggingface-default", provider="hf")
    assert cap.provider == "huggingface"
    assert cap.model_id == "huggingface-default"


def test_data_from_bundled_json_not_hardcoded() -> None:
    """Verify data comes from JSON files, not hardcoded definitions.

    Create a Registry, load bundled data, and check that models from
    the newly added sakura.json and huggingface.json are present.
    This proves the generic JSON loading mechanism works.
    """
    reg = Registry()
    reg._ensure_loaded()
    # sakura.json and huggingface.json are regular JSON files in the data dir
    # that are loaded by _load_bundled() which iterates all *.json files.
    # These providers were NOT in the original codebase - they only exist
    # because we added JSON files.
    sakura_models = reg.list_models(provider="sakura")
    assert len(sakura_models) == 1
    assert sakura_models[0].model_id == "sakura-default"

    hf_models = reg.list_models(provider="huggingface")
    assert len(hf_models) == 1
    assert hf_models[0].model_id == "huggingface-default"
