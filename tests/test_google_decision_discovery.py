"""Google Decisions API metadata is derived from official documentation text."""

import sys
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
