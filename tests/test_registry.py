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
        assert mid not in seen, f"duplicate model_id {mid} in {fname} and {seen[mid]}"
        seen[mid] = fname


# ----------------------------------------------------------------------
# lookup
# ----------------------------------------------------------------------
def test_get_by_id():
    cap = llmcapa.get("gpt-4o")
    assert cap.provider == "openai"
    assert cap.context_window == 128000
    assert cap.supports("vision")


def test_get_by_alias():
    cap = llmcapa.get("gpt-4o-2024-08-06")
    assert cap.model_id == "gpt-4o"


def test_get_case_insensitive():
    assert llmcapa.get("GPT-4O").model_id == "gpt-4o"


def test_get_date_suffix_alias():
    assert llmcapa.get("claude-sonnet-4-5-20250929").model_id == "claude-sonnet-4-5"


def test_get_not_found():
    with pytest.raises(ModelNotFoundError):
        llmcapa.get("no-such-model")


def test_list_models_filter():
    all_models = llmcapa.list_models()
    openai_models = llmcapa.list_models(provider="openai")
    assert openai_models
    assert all(c.provider == "openai" for c in openai_models)
    assert len(all_models) > len(openai_models)


def test_providers():
    provs = llmcapa.providers()
    expected = {
        "openai", "anthropic", "google",
        "xai", "meta", "mistral", "qwen", "deepseek", "nvidia",
        "microsoft", "amazon", "ntt", "customer-cloud", "elyza",
        "softbank", "nec", "fujitsu", "pfn",
    }
    assert expected <= set(provs)


def test_find_by_feature():
    result = llmcapa.find(supports_vision=True, min_context_window=200000)
    assert result
    for cap in result:
        assert cap.supports_vision
        assert cap.context_window >= 200000


def test_find_short_form_flag():
    result = llmcapa.find(reasoning=True)
    assert result
    assert all(c.supports_reasoning for c in result)


def test_find_excludes_deprecated_by_default():
    result = llmcapa.find(provider="openai")
    assert all(not c.deprecated for c in result)


# ----------------------------------------------------------------------
# supports() / extra
# ----------------------------------------------------------------------
def test_supports_modality():
    cap = llmcapa.get("gemini-1.5-pro")
    assert cap.supports("audio")
    assert cap.supports("video")
    assert not llmcapa.get("gpt-4o").supports("video")

    # input/output modality checks
    gpt = llmcapa.get("gpt-4o")
    assert gpt.supports("image_input")
    assert not gpt.supports("image_output")
    assert not gpt.supports("audio_output")

def test_supports_chat_completion_and_responses():
    gpt = llmcapa.get("gpt-4o")
    assert gpt.supports("chat_completion")
    assert gpt.supports("responses_api")
    assert gpt.supports("multimodal")
    assert not gpt.supports("reasoning_effort")

    o1 = llmcapa.get("o1")
    assert o1.supports("reasoning_effort")
    assert not o1.supports("thinking_budget")

    claude = llmcapa.get("claude-3-5-sonnet")
    assert claude.supports("chat_completion")
    assert not claude.supports("responses_api")
    assert claude.supports("multimodal")

    fable = llmcapa.get("claude-fable-5")
    assert fable.supports("thinking_budget")
    assert not fable.supports("reasoning_effort")


def test_capability_extra_roundtrip():
    record = {
        "provider": "x",
        "model_id": "m1",
        "context_window": 10,
        "max_output_tokens": 5,
        "custom_field": 123,
    }
    cap = Capability.from_dict(record)
    assert cap.extra["custom_field"] == 123
    assert cap.supports("custom_field")


# ----------------------------------------------------------------------
# load_extra / register
# ----------------------------------------------------------------------
def test_load_extra_overrides(tmp_path):
    reg = Registry()
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps({"models": [{
        "provider": "openai",
        "model_id": "gpt-4o",
        "context_window": 999,
        "max_output_tokens": 1,
    }]}), encoding="utf-8")
    n = reg.load_extra(extra)
    assert n == 1
    assert reg.get("gpt-4o").context_window == 999


def test_load_extra_list_format(tmp_path):
    reg = Registry()
    extra = tmp_path / "extra.json"
    extra.write_text(json.dumps([{
        "provider": "local",
        "model_id": "my-model",
        "context_window": 4096,
        "max_output_tokens": 1024,
        "aliases": ["mm"],
    }]), encoding="utf-8")
    reg.load_extra(extra)
    assert reg.get("mm").model_id == "my-model"


def test_register():
    reg = Registry()
    reg.register(Capability(provider="t", model_id="t-1", context_window=8))
    assert reg.get("t-1").provider == "t"

def test_fetch_openrouter():
    reg = Registry()
    # Should fetch and register models dynamically
    count = reg.fetch_openrouter()
    assert count > 100
    # Check a standard model is registered
    cap = reg.get("meta-llama/llama-3.3-70b-instruct")
    assert cap.context_window == 131072
    assert cap.supports_chat_completion
    assert cap.pricing is not None
    assert cap.pricing["input_per_1m"] > 0
