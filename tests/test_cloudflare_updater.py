"""Tests for the Cloudflare Workers AI official-docs updater."""

import importlib.util
from pathlib import Path

UPDATER_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "_update_cloudflare_workers_ai.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "cloudflare_workers_ai_updater", UPDATER_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_UPDATER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_UPDATER)


def test_parse_model_index_discovers_ids_from_official_markdown():
    text = """
## Workers AI Models
- [@cf/openai/gpt-oss-20b](https://developers.cloudflare.com/workers-ai/models/gpt-oss-20b/index.md): Reasoning model.
- [@cf/baai/bge-m3](https://developers.cloudflare.com/workers-ai/models/bge-m3/index.md): Embedding model.
"""

    refs = _UPDATER.parse_model_index(text)

    assert [ref["model_id"] for ref in refs] == [
        "@cf/baai/bge-m3",
        "@cf/openai/gpt-oss-20b",
    ]
    assert refs[1]["url"].endswith("/gpt-oss-20b/index.md")


def test_parse_responses_models_uses_official_compatibility_section():
    text = """
### Chat Completions and embeddings
Use `/v1/chat/completions` for text generation.

### Responses API for GPT-OSS
Only [gpt-oss-20b](https://developers.cloudflare.com/workers-ai/models/gpt-oss-20b/)
and [gpt-oss-120b](https://developers.cloudflare.com/workers-ai/models/gpt-oss-120b/)
are supported.

### AI Gateway
Other endpoint details.
"""

    assert _UPDATER.parse_responses_model_slugs(text) == {
        "gpt-oss-20b",
        "gpt-oss-120b",
    }


def test_parse_text_generation_model_uses_explicit_model_page_fields():
    model_id = "@cf/openai/gpt-oss-20b"
    model_ref = {
        "model_id": model_id,
        "url": "https://developers.cloudflare.com/workers-ai/models/gpt-oss-20b/index.md",
        "summary": "Reasoning model",
    }
    page = """---
title: gpt-oss-20b
---
# gpt-oss-20b

Text Generation • OpenAI

`@cf/openai/gpt-oss-20b`

- Cloudflare-hosted
- Batch
- Function calling
- Reasoning

| Model Info | |
| --- | --- |
| Context Window [↗](https://example.test) | 128,000 tokens |
| Function calling [↗](https://example.test) | Yes |
| Reasoning | `low``medium` (default)`high` |
| Unit Pricing | $0.20 per M input tokens, $0.30 per M output tokens |

OpenAI compatible endpoints include `/v1/chat/completions`.

Streaming — Send a request with stream enabled.
"""

    record = _UPDATER.parse_model_page(
        model_ref,
        page,
        responses_model_slugs={"gpt-oss-20b"},
        checked_at="2026-10-06",
    )

    assert record["model_id"] == model_id
    assert record["context_window"] == 128000
    assert record["supports_chat_completion"] is True
    assert record["supports_streaming"] is True
    assert record["supports_function_calling"] is True
    assert record["supports_reasoning"] is True
    assert record["supports_reasoning_effort"] is True
    assert record["supports_responses_api"] is True
    assert record["pricing"] == {
        "input_per_1m": 0.2,
        "output_per_1m": 0.3,
        "currency": "USD",
    }
    assert record["extra"]["cloudflare_task_type"] == "Text Generation"


def test_parse_embedding_and_image_task_types_without_guessing():
    base_ref = "https://developers.cloudflare.com/workers-ai/models/{}/index.md"
    embedding_id = "@cf/baai/bge-m3"
    embedding_page = """---
title: bge-m3
---
# bge-m3

Text Embeddings • BAAI

`@cf/baai/bge-m3`

- Cloudflare-hosted

| Model Info | |
| --- | --- |
| Context Window | 60,000 tokens |
| Unit Pricing | $0.0118 per M input tokens |
"""
    embedding = _UPDATER.parse_model_page(
        {
            "model_id": embedding_id,
            "url": base_ref.format("bge-m3"),
            "summary": "Embedding model",
        },
        embedding_page,
        responses_model_slugs=set(),
        checked_at="2026-10-06",
    )
    assert embedding["output_modalities"] == ["embedding"]
    assert embedding["pricing"]["input_per_1m"] == 0.0118
    assert embedding["supports_chat_completion"] is False

    unknown = _UPDATER.parse_model_page(
        {
            "model_id": "@cf/example/unknown-task",
            "url": base_ref.format("unknown-task"),
            "summary": "Unknown task type",
        },
        "# unknown-task\n\nUnlisted Task • Vendor\n\n`@cf/example/unknown-task`\n",
        responses_model_slugs=set(),
        checked_at="2026-10-06",
    )
    assert unknown["input_modalities"] == []
    assert unknown["output_modalities"] == []
    assert unknown["supports_chat_completion"] is False
    assert unknown["extra"]["cloudflare_task_type"] == "Unlisted Task"


def test_clef_models_keep_decision_metadata_during_official_refresh(monkeypatch):
    base_url = "https://developers.cloudflare.com/workers-ai/models/"
    pages = {
        f"{base_url}{name}/index.md": (
            "---\\ntitle: {name}\\n---\\n# {name}\\n\\n"
            "Text Generation • Cloudflare\\n\\n"
            "`@cf/cloudflare/{name}`\\n\\n"
            "- Cloudflare-hosted\\n- Vision\\n\\n"
            "| Model Info | |\\n| --- | --- |\\n"
            "| Context Window | 65,536 tokens |\\n"
            "| Unit Pricing | ${price:.2f} per M input tokens |\\n"
        ).format(name=name, price=price).replace("\\n", "\n")
        for name, price in (("clef", 0.24), ("clef-flash", 0.09))
    }
    index = "\n".join(
        "- [@cf/cloudflare/{name}]({url}): Decision model".format(
            name=name, url=f"{base_url}{name}/index.md"
        )
        for name in ("clef", "clef-flash")
    )

    def offline_fetch(url):
        if url == _UPDATER.MODEL_INDEX_URL:
            return index
        if url == _UPDATER.OPENAI_COMPAT_URL:
            return "### Responses API\nNo Clef models listed.\n"
        return pages[url]

    monkeypatch.setattr(_UPDATER, "_fetch_text", offline_fetch)
    rows = _UPDATER.fetch_catalog()
    assert len(rows) == 2
    assert [row["model_id"] for row in rows] == [
        "@cf/cloudflare/clef",
        "@cf/cloudflare/clef-flash",
    ]
    for row, price in zip(rows, (0.24, 0.09)):
        assert row["output_modalities"] == ["decision"]
        assert row["supports_chat_completion"] is False
        assert row["supports_responses_api"] is False
        assert row["supports_json_mode"] is False
        assert row["pricing"]["input_per_1m"] == price
        assert row["pricing"]["output_per_1m"] == 0.0
        assert row["decision"]["max_questions"] == 64
        assert row["decision"]["question_kinds"] == ["noul", "choice", "score"]
        assert row["decision"]["endpoints"][0].endswith(row["model_id"])
        assert row["extra"]["endpoints"][0]["protocol"] == "systemone-compatible"


def test_non_decision_model_keeps_generic_cloudflare_mapping():
    row = {
        "model_id": "@cf/example/text-generation",
        "output_modalities": ["text"],
        "pricing": {"input_per_1m": 1.0, "output_per_1m": 2.0},
    }
    assert _UPDATER.enrich_clef_decision(row) is row
    assert row["output_modalities"] == ["text"]
    assert row["pricing"]["output_per_1m"] == 2.0
