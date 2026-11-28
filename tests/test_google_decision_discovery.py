"""Google Decisions API metadata is derived from official documentation text."""

import sys
from html import escape
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import _update_google as updater


def test_parse_decision_model_metadata_from_official_docs():
    model_index = """## Specialized task models

{% table variant="model" %}
  * [Gemini Decision](/docs/models/gemini-decision-1)
  * Fast, calibrated multimodal decisions using the [Decisions API](/docs/decisions-api).
  * `gemini-decision-1`

  ---
{% /table %}
"""
    model_page = """## Gemini Decision

* Model code
* `gemini-decision-1`

* **Inputs** Text, Image, Video, Audio, and PDF
* **Output** Calibrated probabilities (yes/no, choice, and score, with 0 output tokens)
* **Input token limit** 262,144
* **Output token limit** 0 (up to 1,000 questions per request)

* **Single-select:** Evaluates 2 to 255 options
* **Rubric rating:** Evaluates 2 to 255 ordered rubric levels

{% section %}
**Function calling**
{% badge type="not-supported" /%}
{% /section %}
{% section %}
**Structured outputs**
{% badge type="not-supported" /%}
{% /section %}
{% section %}
**Text generation**
{% badge type="not-supported" /%}
{% /section %}
{% section %}
**Thinking**
{% badge type="not-supported" /%}
{% /section %}

[Decisions API](/docs/decisions-api)
"""
    api_page = """## Question types

| Question type | Goal | Returns |
| :--- | :--- | :--- |
| [Yes/no (`noul`)](/docs/decisions-api#noul) | Check a predicate | `noul`, `confidence` |
| [Choice (`choice`)](/docs/decisions-api#choice) | Select an option | `choice`, `probabilities`, `confidence` |
| [Score (`score`)](/docs/decisions-api#score) | Score against a rubric | `score`, `probabilities`, `legend`, `confidence` |

Every question runs against shared input in one forward pass.

```python
input="some state"
input=[{"type": "text", "text": "some state"}]
```

```json
{"answers": {"q": {"type": "noul", "noul": 0.7}}}
```

POST https://generativelanguage.googleapis.com/v1beta/decisions
"""
    pricing_page = """## Gemini Decision  {% id="gemini-decision" %}

[`gemini-decision-1`](/docs/models/gemini-decision-1)

* Input price (text, image, video, audio, PDF)
* Free of charge
* $0.10

---

* Output price
* Not applicable (0 output tokens)
* Not applicable (0 output tokens)
"""

    record = updater.parse_decision_model_docs(
        model_index,
        model_page,
        api_page,
        pricing_page,
    )

    assert record["model_id"] == "gemini-decision-1"
    assert record["context_window"] == 262144
    assert record["max_output_tokens"] == 0
    assert record["input_modalities"] == ["text", "image", "audio", "video"]
    assert record["output_modalities"] == ["decision"]
    assert record["pricing"]["input_per_1m"] == 0.1
    assert record["pricing"]["output_per_1m"] == 0.0
    assert record["decision"]["question_kinds"] == ["noul", "choice", "score"]
    assert record["decision"]["max_questions"] == 1000
    assert record["decision"]["max_total_tokens"] == 262144
    assert record["decision"]["max_questions"] == 1000
    assert record["decision"]["endpoints"] == [
        "https://generativelanguage.googleapis.com/v1beta/decisions"
    ]
    assert record["document"]["input_formats"] == ["pdf"]


def test_discover_prices_from_current_google_markdown_page():
    pricing_markdown = """## Gemini 4 Hydrogen  {% id="gemini-4-hydrogen" %}

{% tabs %}
  {% tab title="Standard" %}
  {% table %}
  * Feature
  * Free Tier
  * Paid Tier, per 1M tokens in USD

  ---

  * Input price
  * Free of charge
  * $1.50

  ---

  * Output price (including thinking tokens)
  * Free of charge
  * $7.50
  {% /table %}
  {% /tab %}
{% /tabs %}
"""
    page_html = f"<noscript><pre>{escape(pricing_markdown)}</pre></noscript>"

    assert updater.discover_prices(page_html) == {
        "gemini-4-hydrogen": (1.5, 7.5, 0)
    }


def test_google_model_token_limits_are_read_from_matching_model_pages():
    model_markdown = """## Gemini 3.8 Flash TTS

* Model code
* `gemini-3.8-flash-tts`

* **Input token limit** 8,192
* **Output token limit** 16,384 (Gemini API serving limit)
"""
    page_html = f"<noscript><pre>{escape(model_markdown)}</pre></noscript>"
    requested = ["gemini-3.8-flash-tts", "gemini-3.8-flash-tts:batch"]
    fetched_urls = []

    limits = updater.discover_model_token_limits(
        requested, fetcher=lambda url: fetched_urls.append(url) or page_html
    )

    expected = {
        "context_window": 8192,
        "max_output_tokens": 16384,
        "source_url": (
            "https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash-tts"
        ),
    }
    assert limits == {model_id: expected for model_id in requested}
    assert fetched_urls == [expected["source_url"]]

    stale = {
        "context_window": 1_048_576,
        "max_output_tokens": 65_536,
        "extra": {"existing": "retained"},
    }
    assert updater.apply_model_token_limits(stale, limits[requested[0]]) is True
    assert stale["context_window"] == 8192
    assert stale["max_output_tokens"] == 16384
    assert stale["extra"]["existing"] == "retained"
    assert stale["extra"]["model_specs_source"] == expected["source_url"]


def test_google_model_token_limit_parser_rejects_mismatched_model_and_unknown_limits():
    page = """* Model code
* `gemini-3.8-flash`
* **Input token limit** 1,048,576
* **Output token limit** 65,536
"""
    assert updater.parse_model_token_limits(page, "gemini-3.7-flash") is None
    assert updater.parse_model_token_limits(
        "* Model code\n* `gemini-3.8-flash`\nNo token limits listed.",
        "gemini-3.8-flash",
    ) is None
    assert updater.template_for("gemini-undocumented-preview")["max_output_tokens"] == 0


def test_google_model_metadata_parser_extracts_modalities_and_explicit_badges():
    page = """* Model code
* `gemini-2.5-flash-native-audio-preview-12-2025`
* **Inputs** Audio, video, text
* **Output** Audio and text
**Function calling**
{% badge type="not-supported" /%}
{% /section %}
**Structured outputs**
{% badge type="not-supported" /%}
{% /section %}
**Thinking**
{% badge type="not-supported" /%}
{% /section %}
"""
    metadata = updater.parse_model_metadata(
        page, "gemini-2.5-flash-native-audio-preview-12-2025"
    )

    assert metadata is not None
    assert metadata["input_modalities"] == ["text", "audio", "video"]
    assert metadata["output_modalities"] == ["text", "audio"]
    assert metadata["supports_audio_input"] is True
    assert metadata["supports_audio_output"] is True
    assert metadata["supports_function_calling"] is False
    assert metadata["supports_json_mode"] is False
    assert metadata["supports_reasoning"] is False


def test_gemini_4_hydrogen_metadata_matches_official_model_page():
    template = updater.template_for("gemini-4-hydrogen")

    assert template["input_modalities"] == ["text", "image", "video", "audio", "file"]
    assert template["supports_vision"] is True
    assert template["supports_reasoning"] is True
    assert template["thinking_level_values"] == ["low", "medium", "high", "xhigh"]
    assert template["max_output_tokens"] == 65_536
    assert template["extra"]["long_decode_max_output_tokens"] == 1_048_576
