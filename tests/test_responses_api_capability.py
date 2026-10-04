from __future__ import annotations

from llmcapa import Capability, ResponsesApiCapability


def test_responses_api_feature_metadata_round_trip() -> None:
    original = Capability(
        provider="example",
        model_id="responses-model",
        supports_responses_api=True,
        responses_api=ResponsesApiCapability(
            previous_response_id=True,
            conversation_state=False,
            streaming=True,
            function_calling=True,
            structured_outputs=None,
            built_in_tools=("web_search", "file_search"),
            extra={"vendor_extension": "enabled"},
        ),
    )

    payload = original.to_dict()
    assert payload["responses_api"]["built_in_tools"] == ["web_search", "file_search"]
    restored = Capability.from_dict(payload)

    assert restored.supports_responses_api is True
    assert restored.responses_api is not None
    assert restored.responses_api.previous_response_id is True
    assert restored.responses_api.conversation_state is False
    assert restored.responses_api.streaming is True
    assert restored.responses_api.function_calling is True
    assert restored.responses_api.structured_outputs is None
    assert restored.responses_api.built_in_tools == ("web_search", "file_search")
    assert restored.responses_api.extra == {"vendor_extension": "enabled"}


def test_legacy_responses_api_flag_remains_compatible() -> None:
    restored = Capability.from_dict(
        {
            "provider": "example",
            "model_id": "legacy-responses-model",
            "supports_responses_api": True,
        }
    )

    assert restored.supports_responses_api is True
    assert restored.responses_api is None
    assert "responses_api" not in restored.to_dict()


def test_unknown_responses_api_fields_are_preserved() -> None:
    restored = ResponsesApiCapability.from_dict(
        {"previous_response_id": True, "future_feature": "supported"}
    )

    assert restored.previous_response_id is True
    assert restored.extra == {"future_feature": "supported"}
    assert restored.to_dict()["extra"] == {"future_feature": "supported"}
