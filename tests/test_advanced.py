import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import llmcapa
from llmcapa import Capability


def test_estimate_cost():
    # Test model with pricing
    gpt = llmcapa.get("gpt-4o")
    assert gpt.pricing is not None

    # input_per_1m = 2.5, output_per_1m = 10.0
    res = gpt.estimate_cost(input_tokens=1000000, output_tokens=1000000)
    assert res["cost"] == 12.5
    assert res["currency"] == "USD"

    # Test model without pricing
    claude = llmcapa.get("claude-3-5-sonnet")
    res2 = claude.estimate_cost(input_tokens=1000, output_tokens=1000)
    assert res2["cost"] == 0.018
    assert res2["currency"] == "USD"


def test_estimate_cost_treats_unknown_rates_as_zero():
    cap = Capability(
        provider="test",
        model_id="unknown-pricing",
        pricing={"input_per_1m": None, "output_per_1m": None, "currency": "USD"},
    )
    assert cap.estimate_cost(input_tokens=1000, output_tokens=1000) == {
        "cost": 0.0,
        "currency": "USD",
    }


def test_can_be_replaced_by():
    gpt4o = llmcapa.get("gpt-4o")
    gpt4o_mini = llmcapa.get("gpt-4o-mini")
    gemini = llmcapa.get("gemini-3.5-flash")

    # gpt-4o and gpt-4o-mini have the same context window (128k) and same features
    # (neither model supports image_output), so gpt-4o can be replaced by gpt-4o-mini.
    assert gpt4o.can_be_replaced_by(gpt4o_mini) is True

    # gemini-3.5-flash has larger context window (1M) but lacks file_input and responses_api.
    # So gpt-4o cannot be replaced by gemini-3.5-flash if we require all features.
    assert gpt4o.can_be_replaced_by(gemini) is False

    # If we only require vision and function_calling, gemini-3.5-flash can replace gpt-4o.
    assert (
        gpt4o.can_be_replaced_by(
            gemini, required_features=["vision", "function_calling"]
        )
        is True
    )

    # Check with specific required features
    assert (
        gpt4o.can_be_replaced_by(
            gpt4o_mini, required_features=["vision", "function_calling"]
        )
        is True
    )


def test_feature_enum():
    from llmcapa import Feature

    gpt4o = llmcapa.get("gpt-4o")
    assert gpt4o.supports(Feature.LLMC_FEAT_VISION) is True
    assert gpt4o.supports(Feature.LLMC_FEAT_REASONING_EFFORT) is False
    assert gpt4o.supports("vision") is True

    from llmcapa import ReasoningEffort

    assert ReasoningEffort.LLMC_EFFORT_LOW == "low"
    assert ReasoningEffort.LLMC_EFFORT_MEDIUM == "medium"
    assert ReasoningEffort.LLMC_EFFORT_HIGH == "high"

    assert ReasoningEffort.LLMC_EFFORT_NONE == "none"
    assert ReasoningEffort.LLMC_EFFORT_MINIMAL == "minimal"
    assert ReasoningEffort.LLMC_EFFORT_XHIGH == "xhigh"


def test_grok47_falls_back_to_grok46_by_provider():
    direct = llmcapa.get("grok-4.7", provider="xai")
    gateway = llmcapa.get("grok-4.7", provider="openrouter")
    assert direct.model_id == "grok-4.6"
    assert gateway.model_id == "x-ai/grok-4.6"
    assert direct.context_window == gateway.context_window == 500000


def test_gpt6_astra_supports_reasoning_effort():
    cap = llmcapa.get("gpt-6-astra")
    assert cap.supports_reasoning_effort is True
    assert cap.supports("reasoning_effort") is True
    assert cap.reasoning_effort_values == ["low", "medium", "high", "xhigh", "max"]


def test_google_thinking_controls_are_provider_specific():
    budget = llmcapa.get("gemini-2.5-flash", provider="google")
    assert budget.supports_thinking_budget is True
    assert budget.get_thinking_budget_values() == {
        "type": "token_range",
        "min": 0,
        "max": 24576,
    }
    assert budget.get_thinking_control()["parameter"] == "thinking_budget"

    level = llmcapa.get("gemini-3-flash-preview", provider="google")
    assert level.supports_thinking_level is True
    assert level.get_thinking_level_values() == ["minimal", "low", "medium", "high"]
    assert level.get_thinking_control()["parameter"] == "thinking_level"


def test_tokenizer_name():
    gpt = llmcapa.get("gpt-4o")
    assert gpt.tokenizer_name == "o200k_base"


def test_estimate_tokens():
    gpt4o = llmcapa.get("gpt-4o")
    gpt4 = llmcapa.get("gpt-4")

    # English
    eng = "Hello world! This is a test."
    assert gpt4o.estimate_tokens(eng) == 8
    assert gpt4.estimate_tokens(eng) == 8

    # Japanese
    jp = "こんにちは世界。これはテストです。"
    assert gpt4o.estimate_tokens(jp) == 8
    assert gpt4.estimate_tokens(jp) == 11

    # Russian (Cyrillic)
    ru = "Привет, мир! Это тест."
    assert gpt4o.estimate_tokens(ru) == 8
    assert gpt4.estimate_tokens(ru) == 12

    # Hindi (Devanagari)
    hi = "नमस्ते दुनिया! यह एक परीक्षण है।"
    assert gpt4o.estimate_tokens(hi) == 11
    assert gpt4.estimate_tokens(hi) == 33


def test_features_list():
    gpt = llmcapa.get("gpt-4o")
    feats = gpt.features()
    assert "vision" in feats
    assert "chat_completion" in feats
    assert "text_input" in feats
    assert "text_output" in feats
    assert "image_input" in feats
    assert "image_output" not in feats
    assert "multimodal" in feats
    assert "reasoning_effort" not in feats

    o1 = llmcapa.get("o1")
    o1_feats = o1.features()
    assert "reasoning_effort" in o1_feats


def test_openrouter_cache(tmp_path, monkeypatch):
    # Mock home directory to use tmp_path
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))

    # First fetch should hit the API and create cache
    count = llmcapa.fetch_openrouter(cache_ttl=3600)
    assert count > 100

    cache_file = tmp_path / ".llmcapa" / "openrouter_cache.json"
    assert cache_file.exists()

    # Modify cache file to verify second fetch reads from cache
    import json

    data = json.loads(cache_file.read_text(encoding="utf-8"))
    # Keep only 1 model in cache
    data = data[:1]
    cache_file.write_text(json.dumps(data), encoding="utf-8")

    # Second fetch with TTL should read from cache (only 1 model registered)
    reg = llmcapa.Registry()
    count2 = reg.fetch_openrouter(cache_ttl=3600)
    assert count2 == 1

    # Verify that Registry initialization automatically loads the cache file if it exists
    reg3 = llmcapa.Registry()
    # Trigger ensure_loaded
    reg3.providers()
    # Since we modified the cache file to only have 1 model, only that model should be registered from OpenRouter
    # (along with other bundled models)
    assert reg3.get("x-ai/grok-build-0.1") is not None


def test_structured_output_capabilities_are_independent_and_nullable():
    unknown = Capability(provider="custom", model_id="unknown")
    assert unknown.supports_json_mode is None
    assert unknown.supports_json_schema is None
    assert unknown.supports("json_schema") is None

    json_only = Capability(
        provider="deepseek",
        model_id="json-only",
        supports_json_mode=True,
        supports_json_schema=False,
    )
    assert json_only.supports("json_mode") is True
    assert json_only.supports("json_schema") is False
    assert json_only.features() and "json_schema" not in json_only.features()

    schema = Capability(
        provider="openai",
        model_id="schema-model",
        supports_json_mode=True,
        supports_json_schema=True,
    )
    assert schema.supports("json_schema") is True
    assert "json_schema" in schema.features()


def test_structured_output_lookup_is_provider_scoped():
    llmcapa.register(
        Capability(
            provider="structured-a",
            model_id="same-model",
            supports_json_mode=True,
            supports_json_schema=True,
        )
    )
    llmcapa.register(
        Capability(
            provider="structured-b",
            model_id="same-model",
            supports_json_mode=True,
            supports_json_schema=False,
        )
    )
    assert llmcapa.supports_json_schema("same-model", "structured-a") is True
    assert llmcapa.supports_json_schema("same-model", "structured-b") is False


def test_capability_roundtrip_preserves_json_schema():
    cap = Capability(
        provider="test",
        model_id="schema-roundtrip",
        supports_json_mode=None,
        supports_json_schema=True,
    )
    restored = Capability.from_dict(cap.to_dict())
    assert restored.supports_json_mode is None
    assert restored.supports_json_schema is True
