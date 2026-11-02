from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _updater():
    path = ROOT / "scripts" / "_update_amazon.py"
    spec = importlib.util.spec_from_file_location("test_amazon_catalog_updater", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    scripts_dir = str(ROOT / "scripts")
    sys.path.insert(0, scripts_dir)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(scripts_dir)
    return module


OPENAI_CARD = """# GPT-6 Luna

## ![OpenAI logo](openai.png) OpenAI — GPT-6 Luna

+ **Model lifecycle:** Active
+ **Context window:** 1,050,000 tokens
+ **Max output tokens:** 128,000
+ **Knowledge cutoff:** May 18, 2026

**Reasoning effort**

Set reasoning effort to low, medium, high, or max.

| **Input modalities** | **Output modalities** |
| --- | --- |
| ![Not supported](icon-no.png) Audio | ![Not supported](icon-no.png) Embedding |
| ![Supported](icon-yes.png) Image | ![Not supported](icon-no.png) Image |
| ![Supported](icon-yes.png) Text | ![Supported](icon-yes.png) Text |

## Endpoints and APIs supported

**Endpoint support**

| **Endpoint** | **Supported** |
| --- | --- |
| bedrock-runtime | ![supported](icon-yes.png) |
| bedrock-mantle | ![supported](icon-yes.png) |

**APIs supported on the `bedrock-runtime` endpoint**

| **Messages** | **Responses** | **Chat Completions** | **Converse** | **Invoke** |
| --- | --- | --- | --- | --- |
| ![not-supported](icon-no.png) | ![supported](icon-yes.png) | ![supported](icon-yes.png) | ![supported](icon-yes.png) | ![supported](icon-yes.png) |

**APIs supported on the `bedrock-mantle` endpoint**

| **Messages** | **Responses** | **Chat Completions** | **Converse** | **Invoke** |
| --- | --- | --- | --- | --- |
| ![not-supported](icon-no.png) | ![supported](icon-yes.png) | ![supported](icon-yes.png) | ![not-supported](icon-no.png) | ![not-supported](icon-no.png) |

**Response streaming** and **JSON Schema output** are supported.

| **Supported** | **Not Supported** |
| --- | --- |
| ![Supported](icon-yes.png) Client-side tool calling | ![Not supported](icon-no.png) Irrelevant feature |

## Call the model

| **Endpoint** | **Model ID** | **In-Region endpoint URL** | **Geo inference ID** | **Global inference ID** |
| --- | --- | --- | --- | --- |
| bedrock-mantle | openai.gpt-6-luna | https://bedrock-mantle.{region}.api.aws/openai/v1 | Not supported | Not supported |
| bedrock-runtime | openai.gpt-6-luna | Not supported | us.openai.gpt-6-luna | global.openai.gpt-6-luna |
"""

AI21_CARD = """# Jamba 1.5 Large

## ![AI21 Labs logo](ai21.png) AI21 Labs — Jamba 1.5 Large

+ **Model lifecycle:** Active
+ **Context window:** 256K tokens
+ **Max output tokens:** 4K
+ **Knowledge cutoff:** Mar 2024

| **Input Modalities** | **Output Modalities** |
| --- | --- |
| ![Supported](icon-yes.png) Text | ![Supported](icon-yes.png) Text |

## Endpoints and APIs supported

**Endpoint support**

| **Endpoint** | **Supported** |
| --- | --- |
| bedrock-runtime | ![supported](icon-yes.png) |
| bedrock-mantle | ![not-supported](icon-no.png) |

**APIs supported on the `bedrock-runtime` endpoint**

| **Messages** | **Responses** | **Chat Completions** | **Converse** | **Invoke** |
| --- | --- | --- | --- | --- |
| ![not-supported](icon-no.png) | ![not-supported](icon-no.png) | ![not-supported](icon-no.png) | ![supported](icon-yes.png) | ![supported](icon-yes.png) |

## Programmatic Access

| **Endpoint** | **Model ID** | **In-Region endpoint URL** |
| --- | --- | --- |
| bedrock-runtime | `ai21.jamba-1-5-large-v1:0` | `https://bedrock-runtime.{region}.amazonaws.com` |
"""


def test_inventory_discovery_and_openai_bedrock_card_parsing():
    updater = _updater()
    index = (
        "[GPT-6 Luna](model-card-openai-gpt-6-luna.md), "
        "[Jamba](model-card-ai21-jamba.md), "
        "[duplicate](model-card-openai-gpt-6-luna.md)"
    )
    assert updater.discover_model_card_urls(index) == [
        updater.BEDROCK_DOCS_BASE + "model-card-openai-gpt-6-luna.md",
        updater.BEDROCK_DOCS_BASE + "model-card-ai21-jamba.md",
    ]

    model = updater.parse_bedrock_model_card(OPENAI_CARD, "https://aws.example/luna")
    assert model is not None
    assert model["provider"] == "amazon"
    assert model["model_id"] == "openai.gpt-6-luna"
    assert model["display_name"] == "GPT-6 Luna"
    assert model["extra"]["bedrock_model_provider"] == "OpenAI"
    assert "nova_pricing" not in model["extra"]
    assert model["context_window"] == 1_050_000
    assert model["max_output_tokens"] == 128_000
    assert model["input_modalities"] == ["image", "text"]
    assert model["output_modalities"] == ["text"]
    assert model["supports_vision"] is True
    assert model["supports_function_calling"] is True
    assert model["supports_chat_completion"] is True
    assert model["supports_responses_api"] is True
    assert model["supports_streaming"] is True
    assert model["supports_json_mode"] is True
    assert model["supports_reasoning"] is True
    assert model["supports_reasoning_effort"] is True
    assert model["aliases"] == [
        "us.openai.gpt-6-luna",
        "global.openai.gpt-6-luna",
    ]
    assert model["extra"]["endpoints"] == [
        {
            "base_url": updater.BEDROCK_RUNTIME_URL,
            "protocol": "aws-bedrock",
            "auth": "sigv4",
            "source": "https://aws.example/luna",
        },
        {
            "base_url": "https://bedrock-mantle.{region}.api.aws/openai/v1",
            "protocol": "aws-bedrock-mantle",
            "auth": "bearer",
            "source": "https://aws.example/luna",
        },
    ]


def test_bedrock_catalog_is_queryable_through_the_registry():
    import llmcapa

    luna = llmcapa.get("openai.gpt-6-luna", provider="bedrock")
    jamba = llmcapa.get("ai21.jamba-1-5-large-v1:0", provider="bedrock")
    assert luna.provider == "amazon"
    assert luna.context_window == 1_050_000
    assert luna.extra["bedrock_model_provider"] == "OpenAI"
    assert jamba.extra["bedrock_model_provider"] == "AI21 Labs"


def test_non_openai_bedrock_cards_are_parsed_and_merged_with_existing_catalog(
    monkeypatch, tmp_path
):
    import json

    updater = _updater()
    jamba = updater.parse_bedrock_model_card(AI21_CARD, "https://aws.example/jamba")
    assert jamba is not None
    assert jamba["model_id"] == "ai21.jamba-1-5-large-v1:0"
    assert jamba["extra"]["bedrock_model_provider"] == "AI21 Labs"
    assert jamba["context_window"] == 256_000
    assert jamba["max_output_tokens"] == 4_000
    assert jamba["supports_chat_completion"] is True
    assert jamba["extra"]["supported_bedrock_endpoints"] == ["bedrock-runtime"]

    catalog = tmp_path / "amazon.json"
    catalog.write_text(
        json.dumps(
            {
                "models": [
                    {
                        "provider": "amazon",
                        "model_id": "openai.gpt-6-luna",
                        "display_name": "old name",
                        "context_window": 1,
                        "supports_function_calling": True,
                        "pricing": {"input_per_1m": 0.5, "output_per_1m": 1.0},
                        "aliases": [],
                        "extra": {"curated_note": "keep"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(updater, "OUT", catalog)
    monkeypatch.setattr(updater, "add_bedrock_claude_models", lambda _models: 0)
    result = updater.build(
        {"nova-micro-v1": {"input": 0.1, "output": 0.2}},
        [
            updater.parse_bedrock_model_card(OPENAI_CARD, "https://aws.example/luna"),
            jamba,
        ],
    )
    by_id = {model["model_id"]: model for model in result}
    luna = by_id["openai.gpt-6-luna"]
    assert luna["display_name"] == "GPT-6 Luna"
    assert luna["context_window"] == 1_050_000
    assert luna["supports_function_calling"] is True
    assert luna["pricing"] == {"input_per_1m": 0.5, "output_per_1m": 1.0}
    assert luna["extra"]["curated_note"] == "keep"
    assert "ai21.jamba-1-5-large-v1:0" in by_id
    assert "nova-micro-v1" in by_id
