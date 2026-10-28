"""Regression coverage for verified vLLM reasoning metadata."""

import llmcapa
from llmcapa.models import Capability
from llmcapa.registry import Registry
from scripts import _update_local_inference_catalogs_from_hf as updater


def _hf_row(model_id: str) -> dict:
    return {
        "model_id": model_id,
        "display_name": model_id,
        "pipeline_tag": "text-generation",
        "input_modalities": ["text"],
        "output_modalities": ["text"],
    }


def test_vllm_reasoning_metadata_exact_match_and_refresh_stability() -> None:
    official = "openai/gpt-oss-20b"
    derivative = "someone/gpt-oss-20b-derivative"
    source = {"models": [_hf_row(official), _hf_row(derivative)]}

    first = updater.build_catalog(source, provider="vllm")
    rows = {item["model_id"]: item for item in first["models"]}
    assert rows[official]["supports_reasoning_effort"] is True
    assert rows[official]["reasoning_effort_values"] == ["low", "medium", "high"]
    assert rows[official]["extra"]["vllm_reasoning_evidence"]["verification"] == (
        "documentation_only"
    )
    assert rows[derivative].get("supports_reasoning_effort") is not True

    second = updater.build_catalog(source, previous=first["models"], provider="vllm")
    assert second["models"] == first["models"]


def test_vllm_reasoning_metadata_does_not_cross_provider_boundaries() -> None:
    source = {"models": [_hf_row("openai/gpt-oss-20b")]}
    other = updater.build_catalog(source, provider="llama-cpp")
    assert other["models"][0].get("supports_reasoning_effort") is not True


def test_bundled_vllm_gpt_oss_efforts_are_documented_levels() -> None:
    for model in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
        cap = llmcapa.get(model, provider="vllm")
        assert cap is not None
        assert cap.supports_reasoning is True
        assert cap.supports_reasoning_effort is True
        assert cap.get_reasoning_effort_values() == ["low", "medium", "high"]
        assert cap.get_thinking_control()["parameter"] == "reasoning_effort"


def test_bundled_vllm_deepseek_v4_has_distinct_efforts() -> None:
    for model in ("deepseek-ai/DeepSeek-V4-Flash", "deepseek-ai/DeepSeek-V4-Pro"):
        cap = llmcapa.get(model, provider="vllm")
        assert cap.supports_reasoning_effort is True
        assert cap.get_reasoning_effort_values() == ["none", "low", "high", "max"]


def test_bundled_vllm_qwen_budget_is_not_reasoning_effort() -> None:
    cap = llmcapa.get("Qwen/Qwen3.6-35B-A3B", provider="vllm")
    assert cap.supports_reasoning is True
    assert cap.supports_reasoning_effort is False
    assert cap.supports_thinking_budget is True
    control = cap.get_thinking_control()
    assert control["kind"] == "budget"
    assert control["parameter"] == "thinking_token_budget"
    assert control["min"] == 1


def test_vllm_refresh_preserves_verified_effort_controls() -> None:
    registry = Registry()
    registry._ensure_loaded()
    stale = Capability(
        provider="vllm",
        model_id="openai/gpt-oss-20b",
        extra={"metadata_source": "huggingface"},
    )
    registry._register_refreshed_catalog_record(stale)
    updated = registry.get("openai/gpt-oss-20b", provider="vllm")
    assert updated.supports_reasoning_effort is True
    assert updated.get_reasoning_effort_values() == ["low", "medium", "high"]
    assert updated.extra["vllm_reasoning_evidence"]["verification"] == (
        "documentation_only"
    )

    # The same canonicalization must apply to cached/explicit registrations.
    registry.register(stale, overwrite=True)
    updated = registry.get("openai/gpt-oss-20b", provider="vllm")
    assert updated.get_reasoning_effort_values() == ["low", "medium", "high"]


def test_vllm_explicit_user_override_is_not_replaced() -> None:
    registry = Registry()
    registry._ensure_loaded()
    custom = Capability(
        provider="vllm",
        model_id="openai/gpt-oss-20b",
        supports_reasoning_effort=False,
        extra={"custom_source": "user"},
    )
    registry.register(custom, overwrite=True)
    cap = registry.get("openai/gpt-oss-20b", provider="vllm")
    assert cap.supports_reasoning_effort is False
    assert cap.extra == {"custom_source": "user"}
