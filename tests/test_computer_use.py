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
