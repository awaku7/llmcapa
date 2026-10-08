"""Bundled Perplexity Router API model catalog tests."""

import llmcapa

EXPECTED_MODELS = {
    "perplexity/kimi-k3",
    "perplexity/glm-5.3",
    "perplexity/glm-5.3-flash",
    "perplexity/nemotron-3-ultra-550b-a55b",
}
ROUTER_CHAT_BASE = "https://api.perplexity.ai/router/v1"


def test_perplexity_router_models_are_registered():
    assert "perplexity-router" in llmcapa.providers()
    models = llmcapa.list_models(provider="perplexity-router")
    assert {model.model_id for model in models} == EXPECTED_MODELS
    assert all(model.provider == "perplexity-router" for model in models)


def test_perplexity_router_endpoints_and_api_surfaces_are_explicit():
    for model_id in EXPECTED_MODELS:
        cap = llmcapa.get(model_id, provider="perplexity-router")

        assert cap.extra["router_api_base_url"] == ROUTER_CHAT_BASE
        assert cap.extra["chat_completions_endpoint"] == (
            f"{ROUTER_CHAT_BASE}/chat/completions"
        )
        assert cap.extra["responses_endpoint"] == f"{ROUTER_CHAT_BASE}/responses"
        assert cap.extra["messages_endpoint"] == (
            "https://api.perplexity.ai/router/v1/messages"
        )
        assert cap.extra["model_catalog_endpoint"] == f"{ROUTER_CHAT_BASE}/models"
        assert cap.extra["router_preview"] is True
        assert cap.supports_chat_completion is True
        assert cap.supports_responses_api is True
        assert cap.supports_anthropic_api is True


def test_perplexity_router_specs_and_rates_match_published_catalog():
    expected = {
        "perplexity/kimi-k3": (1048576, 3.0, 15.0, ["text", "image"]),
        "perplexity/glm-5.3": (1000000, 1.4, 4.4, ["text"]),
        "perplexity/glm-5.3-flash": (1000000, 0.15, 0.5, ["text", "image"]),
        "perplexity/nemotron-3-ultra-550b-a55b": (1000000, 0.25, 2.5, ["text"]),
    }

    for model_id, (context, input_rate, output_rate, modalities) in expected.items():
        cap = llmcapa.get(model_id, provider="perplexity-router")
        assert cap.context_window == context
        assert cap.pricing["input_per_1m"] == input_rate
        assert cap.pricing["output_per_1m"] == output_rate
        assert cap.input_modalities == modalities
        assert cap.output_modalities == ["text"]
        assert cap.extra["native_model_source"]
        assert cap.extra["cache_read_per_1m"] > 0
