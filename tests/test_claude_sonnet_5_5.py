from __future__ import annotations

import llmcapa


def test_claude_sonnet_5_5_catalog() -> None:
    cap = llmcapa.get("claude-sonnet-5-5", provider="anthropic")

    assert cap is not None
    assert cap.provider == "anthropic"
    assert cap.context_window == 1_000_000
    assert cap.max_output_tokens == 128_000
    assert cap.supports("function_calling") is True
    assert cap.supports("vision") is True
    assert cap.supports("reasoning") is True
    assert cap.supports("reasoning_effort") is True
    assert cap.get_reasoning_effort_values() == [
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ]
    assert cap.pricing.input_per_1m == 2.0
    assert cap.pricing.output_per_1m == 10.0


def test_claude_sonnet_5_5_openrouter_style_alias() -> None:
    cap = llmcapa.get("anthropic/claude-sonnet-5-5", provider="anthropic")

    assert cap is not None
    assert cap.model_id == "claude-sonnet-5-5"
