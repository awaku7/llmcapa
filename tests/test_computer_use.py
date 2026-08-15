import json

import llmcapa
from llmcapa.models import Capability, ComputerUseCapability


def test_computer_use_is_optional_and_backward_compatible():
    cap = Capability(provider="test", model_id="model")
    assert cap.computer_use is None
    assert cap.supports("computer_use") is False
    assert "computer_use" not in cap.to_dict()


def test_computer_use_round_trip_is_json_compatible():
    cap = Capability(
        provider="test",
        model_id="model",
        computer_use=ComputerUseCapability(
            supported=True,
            native=True,
            provider="test",
            model="model",
            actions=frozenset({"screenshot", "left_click"}),
            environments=frozenset({"desktop"}),
        ),
    )
    payload = cap.to_dict()
    assert json.loads(json.dumps(payload))["computer_use"]["supported"] is True
    restored = Capability.from_dict(payload)
    assert restored.computer_use == cap.computer_use
    assert restored.supports("computer_use") is True
    assert restored.computer_use.actions == frozenset({"screenshot", "left_click"})


def test_public_computer_use_helpers(monkeypatch):
    registry = llmcapa.Registry()
    registry.register(
        Capability(
            provider="test",
            model_id="model",
            computer_use=ComputerUseCapability(
                supported=True,
                native=False,
                actions=frozenset({"screenshot"}),
                environments=frozenset({"browser"}),
            ),
        )
    )
    monkeypatch.setattr(llmcapa, "default_registry", lambda: registry)
    assert llmcapa.supports_computer_use("model", "test") is True
    assert llmcapa.supports_computer_action("model", "screenshot", "test") is True
    assert llmcapa.supports_computer_action("model", "zoom", "test") is False
    assert llmcapa.supports_computer_environment("model", "browser", "test") is True
    assert llmcapa.supports_computer_environment("model", "desktop", "test") is False


def test_computer_use_checked_at_round_trip():
    cap = ComputerUseCapability(
        supported=True,
        native=True,
        tool_type="computer_20251124",
        tool_version="2025-11-24",
        checked_at="2026-08-15",
    )
    restored = ComputerUseCapability.from_dict(cap.to_dict())
    assert restored.checked_at == "2026-08-15"


def test_computer_use_replacement_is_provider_specific():
    source = Capability(
        provider="anthropic",
        model_id="source",
        computer_use=ComputerUseCapability(
            supported=True,
            native=True,
            api_type="messages",
            tool_type="computer_20251124",
            tool_version="2025-11-24",
            environments=frozenset({"desktop"}),
            actions=frozenset({"screenshot", "left_click"}),
        ),
    )
    same = Capability(
        provider="anthropic",
        model_id="same",
        computer_use=ComputerUseCapability(
            supported=True,
            native=True,
            api_type="messages",
            tool_type="computer_20251124",
            tool_version="2025-11-24",
            environments=frozenset({"desktop", "browser"}),
            actions=frozenset({"screenshot", "left_click", "zoom"}),
        ),
    )
    different_provider = Capability(
        provider="openai",
        model_id="different",
        computer_use=ComputerUseCapability(
            supported=True,
            native=True,
            api_type="responses",
            tool_type="computer",
            environments=frozenset({"desktop"}),
            actions=frozenset({"screenshot", "click"}),
        ),
    )
    assert source.can_be_replaced_by(same, ["computer_use"]) is True
    assert source.can_be_replaced_by(different_provider, ["computer_use"]) is False


def test_computer_use_required_actions_in_replacement():
    source = Capability(
        provider="test",
        model_id="source",
        context_window=100,
    )
    target = Capability(
        provider="test",
        model_id="target",
        context_window=100,
        computer_use=ComputerUseCapability(
            supported=True,
            native=False,
            actions=frozenset({"screenshot", "left_click", "type"}),
        ),
    )
    assert source.can_be_replaced_by(
        target,
        required_actions=["screenshot", "left_click", "type"],
    ) is True
    assert source.can_be_replaced_by(
        target,
        required_actions=["screenshot", "zoom"],
    ) is False


def test_computer_use_tool_version_is_metadata_not_compatibility_gate():
    source = ComputerUseCapability(
        supported=True,
        native=True,
        api_type="messages",
        tool_type="computer",
        tool_version="2025-01-24",
        environments=frozenset({"desktop"}),
        actions=frozenset({"screenshot", "left_click"}),
    )
    target = ComputerUseCapability(
        supported=True,
        native=True,
        api_type="messages",
        tool_type="computer",
        tool_version="2025-11-24",
        environments=frozenset({"desktop"}),
        actions=frozenset({"screenshot", "left_click", "type"}),
    )
    assert source.is_compatible_with(target) is True


def test_computer_use_cross_provider_compatibility_is_not_assumed():
    common_actions = frozenset({"screenshot", "left_click", "type"})
    claude = ComputerUseCapability(
        supported=True,
        native=True,
        provider="anthropic",
        model="claude-sonnet-4-6",
        api_type="messages",
        tool_type="computer_20251124",
        tool_version="2025-11-24",
        environments=frozenset({"desktop"}),
        actions=common_actions,
    )
    gemini = ComputerUseCapability(
        supported=True,
        native=True,
        provider="google",
        model="gemini-3.6-flash",
        api_type="generate_content",
        tool_type="computer_use",
        environments=frozenset({"desktop", "browser", "mobile"}),
        actions=common_actions,
    )
    openai = ComputerUseCapability(
        supported=True,
        native=True,
        provider="openai",
        model="gpt-5.4",
        api_type="responses",
        tool_type="computer",
        environments=frozenset({"desktop", "browser"}),
        actions=common_actions,
    )

    assert claude.is_compatible_with(gemini) is False
    assert gemini.is_compatible_with(claude) is False
    assert claude.is_compatible_with(openai) is False
    assert openai.is_compatible_with(claude) is False
    assert gemini.is_compatible_with(openai) is False
    assert openai.is_compatible_with(gemini) is False


def test_can_be_replaced_by_rejects_cross_provider_computer_use():
    source = Capability(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        computer_use=ComputerUseCapability(
            supported=True,
            native=True,
            provider="anthropic",
            api_type="messages",
            tool_type="computer_20251124",
            environments=frozenset({"desktop"}),
            actions=frozenset({"screenshot", "left_click", "type"}),
        ),
    )
    targets = [
        Capability(
            provider="google",
            model_id="gemini-3.6-flash",
            computer_use=ComputerUseCapability(
                supported=True,
                native=True,
                provider="google",
                api_type="generate_content",
                tool_type="computer_use",
                environments=frozenset({"desktop", "browser"}),
                actions=frozenset({"screenshot", "left_click", "type"}),
            ),
        ),
        Capability(
            provider="openai",
            model_id="gpt-5.4",
            computer_use=ComputerUseCapability(
                supported=True,
                native=True,
                provider="openai",
                api_type="responses",
                tool_type="computer",
                environments=frozenset({"desktop", "browser"}),
                actions=frozenset({"screenshot", "left_click", "type"}),
            ),
        ),
    ]

    for target in targets:
        assert source.can_be_replaced_by(
            target,
            required_features=["computer_use"],
        ) is False
