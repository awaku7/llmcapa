"""Tests for explicit Microsoft Foundry Local catalog import."""

from __future__ import annotations

import json
from io import BytesIO

import pytest

import llmcapa
from llmcapa.registry import Registry


def _catalog_payload() -> dict:
    return {
        "models": [
            {
                "name": "Phi-4-mini-instruct-generic-cuda",
                "displayName": "Phi-4 Mini",
                "alias": "phi-4-mini",
                "publisher": "Microsoft",
                "task": "chat-completion",
                "version": "1",
                "modelType": "ONNX",
                "runtime": {
                    "deviceType": "GPU",
                    "executionProvider": "CUDAExecutionProvider",
                },
                "supportsToolCalling": True,
                "license": "MIT",
                "modelSettings": {
                    "parameters": [
                        {"name": "contextWindow", "value": 131072},
                        {"name": "maxOutputTokens", "value": 4096},
                    ]
                },
            },
            {
                "name": "Phi-4-mini-instruct-generic-cpu",
                "displayName": "Phi-4 Mini",
                "alias": "phi-4-mini",
                "publisher": "Microsoft",
                "task": "chat-completion",
                "version": "1",
                "modelType": "ONNX",
                "runtime": {
                    "deviceType": "CPU",
                    "executionProvider": "CPUExecutionProvider",
                },
                "supportsToolCalling": True,
                "license": "MIT",
                "modelSettings": {
                    "parameters": [
                        {"name": "contextWindow", "value": 131072},
                        {"name": "maxOutputTokens", "value": 4096},
                    ]
                },
            },
            {
                "name": "whisper-small-generic-cpu",
                "displayName": "Whisper Small",
                "alias": "whisper-small",
                "publisher": "OpenAI",
                "task": "automatic-speech-recognition",
                "runtime": {
                    "deviceType": "CPU",
                    "executionProvider": "CPUExecutionProvider",
                },
                "supportsToolCalling": False,
                "license": "MIT",
            },
        ]
    }


def test_fetch_foundry_local_groups_hardware_variants(monkeypatch) -> None:
    payload = json.dumps(_catalog_payload()).encode("utf-8")
    requested_urls: list[str] = []

    def fake_urlopen(request, timeout=None):
        requested_urls.append(request.full_url)
        assert timeout == 3.0
        return BytesIO(payload)

    monkeypatch.setattr("llmcapa.foundry_local.urllib.request.urlopen", fake_urlopen)

    registry = Registry()
    count = llmcapa.fetch_foundry_local(
        "http://localhost:5272/v1", timeout=3.0, registry=registry
    )

    assert count == 2
    assert requested_urls == ["http://localhost:5272/foundry/list"]

    phi = registry.get("phi-4-mini", provider="foundry_local")
    assert phi.provider == "foundry-local"
    assert phi.model_id == "phi-4-mini"
    assert phi.context_window == 131072
    assert phi.max_output_tokens == 4096
    assert phi.supports_function_calling is True
    assert phi.supports_chat_completion is True
    assert phi.supports_streaming is True
    assert len(phi.extra["foundry_local"]["variants"]) == 2
    assert {
        variant["runtime"]["device_type"]
        for variant in phi.extra["foundry_local"]["variants"]
    } == {"CPU", "GPU"}

    cuda_variant = registry.get(
        "Phi-4-mini-instruct-generic-cuda", provider="foundry-local"
    )
    assert cuda_variant.model_id == "phi-4-mini"

    whisper = registry.get("whisper-small", provider="foundry-local")
    assert whisper.input_modalities == ["audio"]
    assert whisper.output_modalities == ["text"]
    assert whisper.supports_chat_completion is False
    assert whisper.supports_function_calling is False


def test_fetch_foundry_local_rejects_non_loopback_endpoints() -> None:
    registry = Registry()
    with pytest.raises(ValueError, match="loopback"):
        llmcapa.fetch_foundry_local("https://example.com:5272", registry=registry)
    with pytest.raises(ValueError, match="path"):
        llmcapa.fetch_foundry_local(
            "http://localhost:5272/not-foundry", registry=registry
        )


def test_fetch_foundry_local_rejects_invalid_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "llmcapa.foundry_local.urllib.request.urlopen",
        lambda request, timeout=None: BytesIO(b'{"unexpected": []}'),
    )
    with pytest.raises(TypeError, match="models list"):
        llmcapa.fetch_foundry_local("http://127.0.0.1:5272", registry=Registry())
