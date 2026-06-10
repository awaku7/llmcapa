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
    assert res2["cost"] == 0.0
    assert res2["currency"] == "USD"

def test_can_be_replaced_by():
    gpt4o = llmcapa.get("gpt-4o")
    gpt4o_mini = llmcapa.get("gpt-4o-mini")
    gemini = llmcapa.get("gemini-3.5-flash")

    # gpt-4o-mini has same context window (128k) but supports fewer features (e.g. no image output)
    # So gpt-4o cannot be replaced by gpt-4o-mini if we require all features
    assert gpt4o.can_be_replaced_by(gpt4o_mini) is False

    # gemini-3.5-flash has larger context window (1M) and supports vision, fc, json, etc.
    # But gemini-3.5-flash does not support image_output (which gpt-4o supports).
    # So gpt-4o cannot be replaced by gemini-3.5-flash if we require all features.
    assert gpt4o.can_be_replaced_by(gemini) is False

    # If we only require vision and function_calling, gemini-3.5-flash can replace gpt-4o.
    assert gpt4o.can_be_replaced_by(gemini, required_features=["vision", "function_calling"]) is True

    # Check with specific required features
    assert gpt4o.can_be_replaced_by(gpt4o_mini, required_features=["vision", "function_calling"]) is True

def test_feature_enum():
    from llmcapa import Feature
    gpt4o = llmcapa.get("gpt-4o")
    assert gpt4o.supports(Feature.LLMC_FEATURE_VISION) is True
    assert gpt4o.supports(Feature.LLMC_FEATURE_REASONING_EFFORT) is False
    assert gpt4o.supports("vision") is True

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
    assert gpt4o.estimate_tokens(jp) == 13
    assert gpt4.estimate_tokens(jp) == 22

    # Russian (Cyrillic)
    ru = "Привет, мир! Это тест."
    assert gpt4o.estimate_tokens(ru) == 9
    assert gpt4.estimate_tokens(ru) == 26

    # Hindi (Devanagari)
    hi = "नमस्ते दुनिया! यह एक परीक्षण है।"
    assert gpt4o.estimate_tokens(hi) == 17
    assert gpt4.estimate_tokens(hi) == 80

def test_features_list():
    gpt = llmcapa.get("gpt-4o")
    feats = gpt.features()
    assert "vision" in feats
    assert "chat_completion" in feats
    assert "text_input" in feats
    assert "text_output" in feats
    assert "image_input" in feats
    assert "image_output" in feats
    assert "multimodal" in feats
    assert "reasoning_effort" not in feats

    o1 = llmcapa.get("o1")
    o1_feats = o1.features()
    assert "reasoning_effort" in o1_feats

def test_openrouter_cache(tmp_path, monkeypatch):
    import os
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
