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

def test_tokenizer_name():
    gpt = llmcapa.get("gpt-4o")
    assert gpt.tokenizer_name == "o200k_base"

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
