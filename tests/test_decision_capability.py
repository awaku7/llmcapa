"""Decision-output (System One) capability tests."""

import llmcapa
from llmcapa import Capability, DecisionCapability


def test_decision_capability_is_optional_and_backward_compatible():
    cap = Capability(provider="test", model_id="text-model")

    assert cap.decision is None
    assert "decision" not in cap.to_dict()
    assert cap.supports("decision_output") is False


def test_decision_capability_round_trip_normalizes_tuples():
    cap = Capability(
        provider="typesafe",
        model_id="round-trip",
        output_modalities=["decision"],
        decision=DecisionCapability(
            decision=True,
            question_kinds=("choice", "score", "noul"),
            answer_fields=("probabilities", "confidence"),
            returns_probabilities=True,
            returns_confidence=True,
            calibrated_confidence=True,
            parallel_questions=True,
            free_form_text=False,
            type_errors_possible=False,
            state_shapes=("string", "json_object", "text_array"),
            max_state_tokens=32000,
            max_total_tokens=64000,
            output_token_billing=False,
            endpoints=("https://api.typesafe.ai/v1/systemone",),
            source_url="https://docs.typesafe.ai/models",
            checked_at="2026-09-19",
        ),
    )

    payload = cap.to_dict()
    assert payload["decision"]["question_kinds"] == ["choice", "score", "noul"]
    assert payload["decision"]["parallel_questions"] is True

    restored = Capability.from_dict(payload)
    assert restored.decision is not None
    assert restored.decision.question_kinds == ("choice", "score", "noul")
    assert restored.decision.state_shapes == ("string", "json_object", "text_array")
    assert restored.decision.max_total_tokens == 64000
    assert restored.decision.endpoints == ("https://api.typesafe.ai/v1/systemone",)
    assert restored.decision == cap.decision


def test_decision_output_replaces_text_output():
    """A decision model does not emit free-form text as its output modality."""
    cap = Capability(
        provider="typesafe",
        model_id="decision-only",
        output_modalities=["decision"],
        supports_json_mode=True,
        decision=DecisionCapability(decision=True, free_form_text=False),
    )

    assert cap.supports("decision") is True
    assert cap.supports("decision_output") is True
    assert cap.supports("text_output") is False
    # A single output modality is not multimodal.
    assert cap.supports("multimodal") is False
    assert "decision_output" in cap.features()


def test_bundled_typesafe_catalog_is_queryable():
    cap = llmcapa.get("jev-1.13.0", provider="typesafe")

    assert cap.input_modalities == ["text"]
    assert cap.output_modalities == ["decision"]
    assert cap.supports("vision") is False
    assert cap.supports("chat_completion") is False
    assert cap.supports("streaming") is False
    assert cap.decision is not None
    assert cap.decision.question_kinds == ("choice", "score", "noul")
    assert cap.decision.calibrated_confidence is True
    assert cap.decision.max_total_tokens == 64000
    assert cap.pricing == {
        "input_per_1m": 0.042,
        "output_per_1m": 0.0,
        "currency": "USD",
    }


def test_typesafe_aliases_and_provider_scoping():
    assert llmcapa.get("jev-latest", provider="typesafe").model_id == "jev-1.13.0"
    assert llmcapa.get("jev-1.13", provider="typesafe").model_id == "jev-1.13.0"
    assert "typesafe" in llmcapa.providers()

    # Unqualified lookup prefers the native catalog over the gateway route.
    assert llmcapa.get("jev-1.13").provider == "typesafe"


def test_openrouter_decision_route_is_scoped_to_the_alpha_endpoint():
    cap = llmcapa.get("typesafe/jev-1.13", provider="openrouter")

    assert cap.provider == "openrouter"
    assert cap.supports("decision_output") is True
    # The Decisions endpoint is not the OpenAI-compatible Responses API.
    assert cap.supports("responses_api") is False
    assert cap.decision.endpoints == ("https://openrouter.ai/api/alpha/decisions",)

    tilde = llmcapa.get("~typesafe/jev-latest", provider="openrouter")
    assert tilde.provider == "openrouter"
    assert tilde.supports("decision_output") is True


def test_decision_model_is_not_replaced_by_a_text_model():
    decision = llmcapa.get("jev-1.13.0", provider="typesafe")
    text = llmcapa.get("gpt-4o", provider="openai")

    assert decision.can_be_replaced_by(text) is False


def test_openai_decisions_api_is_catalogued_on_gpt_6_luna():
    cap = llmcapa.get("gpt-6-luna", provider="openai")

    assert cap.output_modalities == ["text", "decision"]
    assert cap.supports("decision_output") is True
    assert cap.supports("responses_api") is True
    assert cap.decision is not None
    assert cap.decision.question_kinds == ("predicate", "choice", "score")
    assert cap.decision.returns_probabilities is True
    assert cap.decision.parallel_questions is True
    assert cap.decision.output_token_billing is False
    assert cap.decision.endpoints == ("https://api.openai.com/v1/decisions",)
    assert cap.decision.status == "beta"


def test_cloudflare_clef_models_are_typed_decisions_not_chat_models():
    for name, price, params in (
        ("clef", 0.24, 27),
        ("clef-flash", 0.09, 9),
    ):
        model_id = f"@cf/cloudflare/{name}"
        cap = llmcapa.get(model_id, provider="cloudflare")
        assert cap.provider == "cloudflare-workers-ai"
        assert cap.context_window == 65_536
        assert cap.max_output_tokens == 0
        assert cap.input_modalities == ["text", "image"]
        assert cap.output_modalities == ["decision"]
        assert cap.supports("decision_output") is True
        assert cap.supports("text_output") is False
        assert cap.supports("vision") is True
        assert cap.supports_chat_completion is False
        assert cap.supports_responses_api is False
        assert cap.supports_function_calling is False
        assert cap.supports_json_mode is False
        assert cap.supports_json_schema is False
        assert cap.pricing == {
            "input_per_1m": price,
            "output_per_1m": 0.0,
            "currency": "USD",
        }
        assert cap.estimate_cost(1_000_000, 0)["cost"] == price
        assert cap.decision is not None
        assert cap.decision.question_kinds == ("noul", "choice", "score")
        assert cap.decision.returns_probabilities is True
        assert cap.decision.parallel_questions is True
        assert cap.decision.max_total_tokens == 65_536
        assert cap.decision.max_questions == 64
        assert cap.decision.output_token_billing is False
        assert cap.decision.free_form_text is False
        assert cap.decision.endpoints == (
            "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/"
            + model_id,
        )
        assert cap.extra["parameters_billion"] == params
        assert cap.extra["max_images"] == 4
        assert cap.extra["open_weights_license"] == "Apache-2.0"
        assert llmcapa.get(name, provider="workers-ai").model_id == model_id
        assert llmcapa.get(
            f"cloudflare/{name}", provider="cloudflare-workers-ai"
        ).model_id == model_id
        assert Capability.from_dict(cap.to_dict()).decision == cap.decision


def test_cloudflare_clef_is_registered_in_existing_provider_catalog():
    models = llmcapa.list_models(provider="cloudflare-workers-ai")
    ids = {cap.model_id for cap in models}
    assert "@cf/cloudflare/clef" in ids
    assert "@cf/cloudflare/clef-flash" in ids
    assert all(
        llmcapa.get(mid, provider="cloudflare").supports("decision_output")
        for mid in ("@cf/cloudflare/clef", "@cf/cloudflare/clef-flash")
    )
