"""Update google.json from Google's published Gemini pricing tables.

Model IDs and token prices are discovered from the official page at runtime;
existing catalog metadata is preserved where the page does not provide it.
"""

from __future__ import annotations

import json
import re
import shutil
import ssl
from copy import deepcopy
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from _computer_use_metadata import (
    GOOGLE_COMPUTER_USE_SHUTDOWNS,
    google_computer_use_capability,
)

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "google.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "google.json"
)
SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"
MODEL_INDEX_SOURCE = "https://aistudio.google.com/docs/models"
PRICING_SOURCE = "https://aistudio.google.com/docs/pricing"


def normalize_native_endpoint(model: dict) -> None:
    """Mark Google Gemini entries as using the native Google API."""
    extra = model.get("extra") or {}
    endpoints = extra.get("endpoints") or []
    for endpoint in endpoints:
        base_url = str(endpoint.get("base_url") or "")
        if "generativelanguage.googleapis.com" in base_url:
            endpoint["protocol"] = "google-generative-language"
            endpoint["auth"] = "api-key"
    if endpoints:
        extra["endpoints"] = endpoints
        model["extra"] = extra


def fetch(url: str) -> str:
    """Fetch a Google documentation page (with a controlled TLS fallback)."""
    request = Request(url, headers={"User-Agent": "llmcapa-google-updater/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", "replace")
    except (ssl.SSLCertVerificationError, URLError) as exc:
        reason = getattr(exc, "reason", exc)
        if not isinstance(reason, ssl.SSLCertVerificationError):
            raise
        # Some corporate MITM certificates are rejected by Python's validator.
        # Keep the fallback explicit and limited to this public documentation fetch.
        context = ssl._create_unverified_context()
        with urlopen(request, context=context, timeout=30) as response:
            return response.read().decode("utf-8", "replace")


def parse_price(cell: str) -> float | None:
    match = re.search(r"\$([0-9]+(?:\.[0-9]+)?)", cell.replace(",", ""))
    return float(match.group(1)) if match else None


def discover_prices(
    page_html: str | None = None,
) -> dict[str, tuple[float, float, int]]:
    """Read model IDs and current token prices from Google's pricing tables."""
    html = page_html if page_html is not None else fetch(SOURCE)
    headings = list(
        re.finditer(
            r'<h2 id="([^"]+)"[^>]*>.*?</h2>\s*<em>.*?<code[^>]*>([^<]+)</code>',
            html,
            re.DOTALL,
        )
    )
    discovered: dict[str, tuple[float, float, int]] = {}

    # Google now publishes the pricing page's source as Markdown embedded in
    # the docs HTML. The older rendered-table markup above is still supported
    # for cached/legacy pages, but does not contain the current Gemini 4 rows.
    if not headings:
        markdown = google_docs_markdown(html)
        markdown_headings = list(
            re.finditer(r'(?m)^##\s+.*?\{%\s*id="(gemini-[^"]+)"\s*%\}', markdown)
        )
        for index, heading in enumerate(markdown_headings):
            model_id = heading.group(1)
            section_end = (
                markdown_headings[index + 1].start()
                if index + 1 < len(markdown_headings)
                else len(markdown)
            )
            section = markdown[heading.start() : section_end]
            standard_tab = re.search(
                r'\{%\s*tab title="Standard"\s*%\}(.*?)\{%\s*/tab\s*%\}',
                section,
                re.DOTALL,
            )
            if not standard_tab:
                continue

            def markdown_price(
                label: str, source: str = standard_tab.group(1)
            ) -> float | None:
                row = re.search(
                    rf"(?m)^\s*\*\s*{label}[^\n]*\n\s*\*\s*[^\n]*\n\s*\*\s*([^\n]+)",
                    source,
                    re.IGNORECASE,
                )
                return parse_price(row.group(1)) if row else None

            inp = markdown_price("Input price")
            out = markdown_price("Output price")
            if inp is not None and out is not None:
                discovered[model_id] = (inp, out, 1_048_576)
        return discovered

    for index, match in enumerate(headings):
        model_id = match.group(2).strip()
        if not model_id.startswith("gemini-"):
            continue
        section_end = (
            headings[index + 1].start() if index + 1 < len(headings) else len(html)
        )
        section = html[match.start() : section_end]

        def paid_price(label: str, source: str = section) -> float | None:
            row = re.search(
                rf"<tr>.*?{label}.*?</tr>", source, re.DOTALL | re.IGNORECASE
            )
            if not row:
                return None
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(0), re.DOTALL)
            return parse_price(cells[-1]) if cells else None

        inp, out = paid_price("Input price"), paid_price("Output price")
        if inp is not None and out is not None:
            discovered[model_id] = (inp, out, 1_048_576)
    return discovered


def discover_metadata(html: str) -> tuple[dict[str, dict], dict[str, str]]:
    """Extract non-token prices and shutdown dates from each official model section."""
    headings = list(
        re.finditer(
            r'<h2 id="([^"]+)"[^>]*>.*?</h2>\s*<em>.*?<code[^>]*>([^<]+)</code>',
            html,
            re.DOTALL,
        )
    )
    extras: dict[str, dict] = {}
    deprecations: dict[str, str] = {}
    for index, match in enumerate(headings):
        model_id = match.group(2).strip()
        section_end = (
            headings[index + 1].start() if index + 1 < len(headings) else len(html)
        )
        section = html[match.start() : section_end]
        extra: dict = {"source": SOURCE, "discovered_from": SOURCE}
        for label, key in (
            ("Image output", "image_output_per_1m"),
            ("Video output", "video_output_per_1m"),
        ):
            row = re.search(
                rf"<tr>.*?{label}.*?</tr>", section, re.DOTALL | re.IGNORECASE
            )
            if row:
                cells = re.findall(r"<td[^>]*>(.*?)</td>", row.group(0), re.DOTALL)
                value = parse_price(cells[-1]) if cells else None
                if value is not None:
                    extra[key] = value
        song = re.search(
            r"\$([0-9]+(?:\.[0-9]+)?)\s*(?:per|/)?\s*song", section, re.IGNORECASE
        )
        if song:
            extra.update({"price_per_song": float(song.group(1)), "unit": "song"})
        if len(extra) > 2:
            extras[model_id] = extra
        retired = re.search(
            r"(?:shutdown|shut down|discontinu\w*).*?(20\d{2}-\d{2}-\d{2}|[A-Z][a-z]+ \d{1,2},? 20\d{2})",
            section,
            re.IGNORECASE | re.DOTALL,
        )
        if retired:
            date = retired.group(1)
            try:
                date = (
                    datetime.strptime(date, "%B %d, %Y")
                    .replace(tzinfo=timezone.utc)
                    .strftime("%Y-%m-%d")
                )
            except ValueError:
                pass
            deprecations[model_id] = date
    return extras, deprecations


def google_docs_markdown(page_html: str) -> str:
    """Extract the public Markdown payload embedded in a Google docs page."""
    match = re.search(
        r"<noscript>\s*<pre>(.*?)</pre>\s*</noscript>",
        page_html,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        raise ValueError("Google docs page has no embedded Markdown content")
    return unescape(match.group(1))


def discover_decision_model_index(
    markdown: str, *, source: str = MODEL_INDEX_SOURCE
) -> tuple[str, str, str]:
    """Find the specialized Decisions API model from Google's official model index."""
    rows = re.finditer(r"(?m)^\s*\*\s+\[([^\]]+)\]\(([^)]+)\)", markdown)
    for match in rows:
        separator = re.search(r"(?m)^\s*---\s*$", markdown[match.end() :])
        end = match.end() + separator.start() if separator else len(markdown)
        row = markdown[match.start() : end]
        if (
            "decision" not in match.group(1).lower()
            or "decisions api" not in row.lower()
        ):
            continue
        codes = re.findall(r"`([^`]+)`", row)
        if codes:
            return (
                codes[-1].strip(),
                match.group(1).strip(),
                urljoin(source, match.group(2)),
            )
    raise ValueError("official Google model index has no Decisions API model row")


def _markdown_sections(markdown: str) -> list[tuple[str, str]]:
    headings = list(re.finditer(r"(?m)^##\s+(.+)$", markdown))
    sections = []
    for index, heading in enumerate(headings):
        end = (
            headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        )
        sections.append((heading.group(1), markdown[heading.start() : end]))
    return sections


def _documented_capability(markdown: str, name: str) -> bool | None:
    """Read a supported/not-supported badge from the official model page."""
    match = re.search(
        rf"\*\*{re.escape(name)}\*\*(.*?)(?=\{{%\s*/section\s*%\}})",
        markdown,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    badge = re.search(
        r'\{%\s*badge\s+type="(supported|not-supported)"\s*/%\}',
        match.group(1),
        re.IGNORECASE,
    )
    if not badge:
        return None
    return badge.group(1).lower() == "supported"


def parse_decision_model_docs(
    index_markdown: str,
    model_markdown: str,
    api_markdown: str,
    pricing_markdown: str,
    *,
    index_source: str = MODEL_INDEX_SOURCE,
    pricing_source: str = PRICING_SOURCE,
) -> dict:
    """Build the typed-decision record by parsing Google's official docs."""
    model_id, display_name, model_url = discover_decision_model_index(
        index_markdown, source=index_source
    )
    code_label = re.search(r"\bModel code\b", model_markdown, re.IGNORECASE)
    model_code = (
        re.search(r"`([^`]+)`", model_markdown[code_label.end() :])
        if code_label
        else None
    )
    if not model_code or model_code.group(1).strip() != model_id:
        raise ValueError(
            "Google model page code disagrees with the official model index"
        )

    input_match = re.search(
        r"(?m)^\s*(?:\*\s*)?\*\*Inputs\*\*[ 	]*(.*)$", model_markdown, re.IGNORECASE
    )
    output_match = re.search(
        r"(?m)^\s*(?:\*\s*)?\*\*Output\*\*[ 	]*(.*)$", model_markdown, re.IGNORECASE
    )
    input_limit = re.search(
        r"\*\*Input token limit\*\*[ 	]*([\d,]+)", model_markdown, re.IGNORECASE
    )
    output_limit = re.search(
        r"\*\*Output token limit\*\*[ 	]*([\d,]+)", model_markdown, re.IGNORECASE
    )
    max_questions = re.search(
        r"up to\s+([\d,]+)\s+questions(?:\s+per request)?",
        model_markdown,
        re.IGNORECASE,
    )
    if not all((input_match, output_match, input_limit, output_limit, max_questions)):
        raise ValueError("Google model page is missing modalities or token limits")

    input_types = input_match.group(1)
    input_modalities = [
        name
        for name in ("text", "image", "audio", "video")
        if re.search(rf"\b{name}\b", input_types, re.IGNORECASE)
    ]
    accepts_pdf = bool(re.search(r"\bpdf\b", input_types, re.IGNORECASE))
    if (
        not input_modalities
        or "decision" not in display_name.lower()
        or "probabilit" not in output_match.group(1).lower()
    ):
        raise ValueError("Google model page does not describe typed-decision output")
    input_tokens = int(input_limit.group(1).replace(",", ""))
    output_tokens = int(output_limit.group(1).replace(",", ""))
    question_limit = int(max_questions.group(1).replace(",", ""))

    question_kinds: list[str] = []
    answer_fields: list[str] = []
    in_question_table = False
    for line in api_markdown.splitlines():
        if not line.lstrip().startswith("|"):
            if in_question_table:
                break
            continue
        columns = [column.strip() for column in line.strip().strip("|").split("|")]
        if len(columns) != 3:
            continue
        if "question type" in columns[0].lower() and "returns" in columns[2].lower():
            in_question_table = True
            continue
        if not in_question_table:
            continue
        kind = re.search(r"`([^`]+)`", columns[0])
        if not kind:
            continue
        question_kinds.append(kind.group(1))
        answer_fields.extend(re.findall(r"`([^`]+)`", columns[2]))
    question_kinds = list(dict.fromkeys(question_kinds))
    answer_fields = list(dict.fromkeys(answer_fields))
    if not question_kinds or not answer_fields:
        raise ValueError("Decisions API docs lack typed question/answer tables")
    if re.search(r'["\']type["\']\s*:', api_markdown):
        answer_fields.insert(0, "type")

    endpoint_match = re.search(
        r"https://[A-Za-z0-9.-]+/v[0-9]+(?:alpha|beta)?/decisions", api_markdown
    )
    if not endpoint_match:
        raise ValueError("Decisions API docs lack a versioned endpoint URL")
    endpoint = endpoint_match.group(0)
    endpoint_parts = urlsplit(endpoint)
    endpoint_path = endpoint_parts.path
    base_url = endpoint.rsplit("/", 1)[0]
    api_version_match = re.search(r"/(v[0-9]+(?:alpha|beta)?)/", endpoint_path)
    if not api_version_match:
        raise ValueError("could not parse the documented Decisions API version")
    api_version = api_version_match.group(1)

    api_link = re.search(r"\[Decisions API\]\(([^)]+)\)", model_markdown, re.IGNORECASE)
    api_source = urljoin(model_url, api_link.group(1)) if api_link else None
    pricing_match = next(
        (
            (heading, section)
            for heading, section in _markdown_sections(pricing_markdown)
            if model_id in section and re.search(r"Input price", section, re.IGNORECASE)
        ),
        None,
    )
    if not pricing_match:
        raise ValueError("official pricing page has no section for the listed model")
    pricing_heading, pricing_section = pricing_match
    input_price = None
    for table in re.split(r"(?m)^\s*---\s*$", pricing_section):
        cells = [
            line.strip()[1:].strip()
            for line in table.splitlines()
            if re.match(r"^\s*\*\s+", line)
        ]
        if cells and re.match(r"Input price\b", cells[0], re.IGNORECASE):
            input_price = parse_price(cells[-1])
            break
    if input_price is None:
        raise ValueError(
            "official pricing page has no numeric input price for the model"
        )
    pricing_anchor = re.search(r'\{%\s*id="([^"]+)"\s*%\}', pricing_heading)
    pricing_url = (
        f"{pricing_source}#{pricing_anchor.group(1)}"
        if pricing_anchor
        else pricing_source
    )

    choice_max = re.search(
        r"Evaluates\s+\d+\s+to\s+([\d,]+)\s+options", model_markdown, re.IGNORECASE
    )
    score_max = re.search(
        r"Evaluates\s+\d+\s+to\s+([\d,]+)\s+ordered rubric levels",
        model_markdown,
        re.IGNORECASE,
    )
    checked_at = datetime.now(timezone.utc).date().isoformat()
    thinking = _documented_capability(model_markdown, "Thinking")
    function_calling = _documented_capability(model_markdown, "Function calling")
    structured_outputs = _documented_capability(model_markdown, "Structured outputs")
    text_generation = _documented_capability(model_markdown, "Text generation")
    state_shapes = []
    if re.search(r"\binput\s*=\s*['\"]", api_markdown):
        state_shapes.append("string")
    if re.search(r"\binput\s*=\s*\[", api_markdown):
        state_shapes.append("content_array")

    return {
        "provider": "google",
        "model_id": model_id,
        "display_name": display_name,
        "context_window": input_tokens,
        "max_output_tokens": output_tokens,
        "input_modalities": input_modalities,
        "output_modalities": ["decision"],
        "supports_function_calling": function_calling,
        "supports_json_mode": structured_outputs,
        "supports_json_schema": structured_outputs,
        "supports_streaming": None,
        "supports_vision": "image" in input_modalities,
        "supports_reasoning": None,
        "supports_chat_completion": text_generation,
        "supports_responses_api": None,
        "supports_reasoning_effort": thinking,
        "reasoning_effort_values": None,
        "supports_thinking_budget": thinking,
        "thinking_budget_values": None,
        "supports_thinking_level": thinking,
        "thinking_level_values": None,
        "thinking_control": None,
        "supports_anthropic_api": None,
        "supports_google_api": True,
        "supports_fim": None,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": {
            "input_per_1m": input_price,
            "output_per_1m": 0.0 if output_tokens == 0 else None,
            "currency": "USD",
        },
        "deprecated": False,
        "aliases": [],
        "extra": {
            "endpoints": [
                {
                    "base_url": base_url,
                    "protocol": "google-generative-language",
                    "auth": "api-key",
                    "source": api_source or model_url,
                }
            ],
            "source": model_url,
            "pricing_source": pricing_url,
        },
        "decision": {
            "decision": True,
            "question_kinds": question_kinds,
            "answer_fields": answer_fields,
            "returns_probabilities": "probabilities" in answer_fields,
            "returns_confidence": "confidence" in answer_fields,
            "calibrated_confidence": None,
            "parallel_questions": bool(
                re.search(r"one forward pass", api_markdown, re.IGNORECASE)
            ),
            "free_form_text": output_tokens > 0,
            "type_errors_possible": None,
            "deterministic": None,
            "state_shapes": state_shapes,
            "max_state_tokens": None,
            "max_total_tokens": input_tokens,
            "output_token_billing": output_tokens > 0,
            "max_questions": question_limit,
            "cardinality_max": None,
            "endpoints": [endpoint],
            "source_url": api_source,
            "checked_at": checked_at,
            "status": "documented",
            "extra": {
                "endpoint_protocol": f"google-gemini-decisions-{api_version}",
                "endpoint_path": endpoint_path,
                "api_version": api_version,
                "max_input_tokens": input_tokens,
                "max_choice_options": (
                    int(choice_max.group(1).replace(",", "")) if choice_max else None
                ),
                "max_score_levels": (
                    int(score_max.group(1).replace(",", "")) if score_max else None
                ),
                "output_tokens": output_tokens,
            },
        },
        "document": {
            "accepts_file": accepts_pdf,
            "input_formats": ["pdf"] if accepts_pdf else [],
            "input_mime_types": ["application/pdf"] if accepts_pdf else [],
            "source_url": model_url,
            "checked_at": checked_at,
            "status": "documented",
        },
    }


def discover_decision_model(pricing_html: str) -> dict:
    """Discover the Decisions API model entirely from Google's official docs."""
    index_markdown = google_docs_markdown(fetch(MODEL_INDEX_SOURCE))
    model_id, _display_name, model_url = discover_decision_model_index(index_markdown)
    model_markdown = google_docs_markdown(fetch(model_url))
    api_link = re.search(r"\[Decisions API\]\(([^)]+)\)", model_markdown, re.IGNORECASE)
    if not api_link:
        raise ValueError("official model page does not link to the Decisions API docs")
    api_markdown = google_docs_markdown(fetch(urljoin(model_url, api_link.group(1))))
    record = parse_decision_model_docs(
        index_markdown,
        model_markdown,
        api_markdown,
        google_docs_markdown(pricing_html),
    )
    if record["model_id"] != model_id:
        raise ValueError("discovered model ID changed between official docs pages")
    return record


def template_for(model_id: str) -> dict:
    """Build conservative metadata for a newly documented Gemini model."""
    display = model_id.replace("-", " ").title()
    # Gemini's native API exposes thinking_budget for Gemini 2.5 and
    # thinking_level for Gemini 3+. reasoning_effort is an OpenAI parameter,
    # not a native Google API parameter, so it must not be advertised here.
    is_specialized = any(tag in model_id for tag in ("-image", "-tts", "-native-audio"))
    is_gemini_25_thinking = (
        re.match(r"^gemini-2\.5(?:-|$)", model_id) is not None and not is_specialized
    )
    # The official thinking-level matrix differs by Gemini generation.
    # The 3.8 live model does not expose thinking levels; its extended-
    # thinking counterpart and Gemini 4 Argon accept low/medium/high only.
    modern_level_models = {
        "gemini-3.8-flash",
        "gemini-3.8-live-extended-thinking",
        "gemini-4-argon",
    }
    is_hydrogen = model_id == "gemini-4-hydrogen"
    is_modern_level = model_id in modern_level_models or is_hydrogen
    is_gemini_3_thinking = (
        re.match(r"^gemini-3(?:\.|-|$)", model_id) is not None
        and not is_specialized
        and not model_id.startswith("gemini-3.8-")
    )
    budget_values = (
        {"type": "token_range", "min": 0, "max": 24576}
        if is_gemini_25_thinking
        else None
    )
    level_values = (
        ["low", "medium", "high", "xhigh"]
        if is_hydrogen
        else (
            ["low", "medium", "high"]
            if is_modern_level
            else (
                ["minimal", "low", "medium", "high"] if is_gemini_3_thinking else None
            )
        )
    )
    control = (
        {
            "kind": "budget",
            "parameter": "thinking_budget",
            **budget_values,
        }
        if budget_values
        else (
            {
                "kind": "level",
                "parameter": "thinking_level",
                "values": level_values,
            }
            if level_values
            else None
        )
    )
    extra = {"source": SOURCE, "discovered_from": SOURCE}
    if is_hydrogen:
        extra.update(
            {
                "source": "https://ai.google.dev/gemini-api/docs/models/gemini-4-hydrogen",
                "long_decode_max_output_tokens": 1_048_576,
                "long_decode_requires_opt_in": True,
            }
        )
    return {
        "display_name": display,
        "input_modalities": (
            ["text", "image", "video", "audio", "file"] if is_hydrogen else ["text"]
        ),
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_vision": is_hydrogen
        or any(x in model_id for x in ("image", "vision")),
        "supports_reasoning": is_hydrogen
        or any(x in model_id for x in ("pro", "flash")),
        "supports_chat_completion": True,
        "supports_reasoning_effort": False,
        "reasoning_effort_values": None,
        "supports_thinking_budget": is_gemini_25_thinking,
        "thinking_budget_values": budget_values,
        "supports_thinking_level": level_values is not None,
        "thinking_level_values": level_values,
        "thinking_control": control,
        "max_output_tokens": 65_536,
        "extra": extra,
    }


def base_model(
    model_id: str, template: dict, price_tuple: tuple[float, float, int]
) -> dict:
    inp, out, ctx = price_tuple
    return {
        "provider": "google",
        "model_id": model_id,
        "display_name": template.get("display_name", model_id),
        "context_window": ctx,
        "max_output_tokens": template.get("max_output_tokens", 8192),
        "input_modalities": template.get("input_modalities", ["text"]),
        "output_modalities": template.get("output_modalities", ["text"]),
        "supports_function_calling": template.get("supports_function_calling", True),
        "supports_json_mode": template.get("supports_json_mode", True),
        "supports_streaming": True,
        "supports_vision": template.get("supports_vision", False),
        "supports_reasoning": template.get("supports_reasoning", False),
        "supports_chat_completion": template.get("supports_chat_completion", True),
        "supports_responses_api": False,
        "supports_reasoning_effort": template.get("supports_reasoning_effort", False),
        "supports_thinking_budget": template.get("supports_thinking_budget", False),
        "supports_anthropic_api": False,
        "supports_google_api": True,
        "supports_fim": False,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"},
        "deprecated": False,
        "aliases": [],
        "reasoning_effort_values": template.get("reasoning_effort_values"),
        "thinking_budget_values": template.get("thinking_budget_values"),
        "supports_thinking_level": template.get("supports_thinking_level", False),
        "thinking_level_values": template.get("thinking_level_values"),
        "thinking_control": template.get("thinking_control"),
        "extra": deepcopy(template.get("extra") or {}),
    }


def reconcile_computer_use(models: list[dict]) -> None:
    """Apply Google's current official Computer Use compatibility list."""
    for model in models:
        model_id = str(model.get("model_id", ""))
        capability = google_computer_use_capability(model_id, "google")
        if capability is not None:
            model["computer_use"] = capability
        elif model_id in GOOGLE_COMPUTER_USE_SHUTDOWNS:
            model["deprecated"] = True
            extra = model.get("extra") or {}
            extra["computer_use_shutdown_date"] = GOOGLE_COMPUTER_USE_SHUTDOWNS[
                model_id
            ]
            extra["computer_use_source_url"] = (
                "https://ai.google.dev/gemini-api/docs/deprecations"
            )
            model["extra"] = extra
            model.pop("computer_use", None)
        elif (
            model_id.startswith("gemini-3")
            and (model.get("computer_use") or {}).get("source_url")
            == "https://ai.google.dev/gemini-api/docs/generate-content/computer-use"
        ):
            model.pop("computer_use", None)


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = data["models"]
    by_id = {m["model_id"]: m for m in models}
    pricing_html = fetch(SOURCE)
    decision_model = discover_decision_model(pricing_html)
    google_prices = discover_prices(pricing_html)
    discovered_extras, discovered_deprecations = discover_metadata(pricing_html)

    updated = 0
    inserted = 0
    specialty = 0
    deprecated_n = 0

    decision_model_id = decision_model["model_id"]
    previous_decision = by_id.get(decision_model_id)
    if previous_decision is None:
        models.append(decision_model)
        by_id[decision_model_id] = decision_model
        inserted += 1
    elif previous_decision != decision_model:
        models[models.index(previous_decision)] = decision_model
        by_id[decision_model_id] = decision_model
        updated += 1

    # Update existing prices / context
    for mid, (inp, out, ctx) in google_prices.items():
        if mid not in by_id:
            continue
        m = by_id[mid]
        m["pricing"] = {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"}
        if not m.get("context_window"):
            m["context_window"] = ctx
        m["supports_google_api"] = True
        m["supports_responses_api"] = False
        m["supports_fim"] = False
        updated += 1

    # Refresh native Google thinking controls for existing, imported, and
    # batch records too. reasoning_effort is intentionally disabled because
    # this catalog describes the native Google API.
    for model in models:
        tmpl = template_for(model["model_id"])
        model["supports_reasoning_effort"] = False
        model["reasoning_effort_values"] = None
        model["supports_thinking_budget"] = tmpl.get("supports_thinking_budget", False)
        model["thinking_budget_values"] = tmpl.get("thinking_budget_values")
        model["supports_thinking_level"] = tmpl.get("supports_thinking_level", False)
        model["thinking_level_values"] = tmpl.get("thinking_level_values")
        model["thinking_control"] = tmpl.get("thinking_control")

    # Insert missing models that have templates
    for mid in google_prices:
        tmpl = template_for(mid)
        if mid in by_id:
            # still ensure price applied
            if mid in google_prices:
                inp, out, ctx = google_prices[mid]
                by_id[mid]["pricing"] = {
                    "input_per_1m": inp,
                    "output_per_1m": out,
                    "currency": "USD",
                }
                if not by_id[mid].get("context_window"):
                    by_id[mid]["context_window"] = ctx
            continue
        if mid not in google_prices:
            continue
        new_m = base_model(mid, tmpl, google_prices[mid])
        models.append(new_m)
        by_id[mid] = new_m
        inserted += 1

    # Apply non-token prices discovered from the same official page.
    for mid, extra_patch in discovered_extras.items():
        if mid not in by_id:
            continue
        extra = by_id[mid].get("extra") or {}
        extra.update(extra_patch)
        by_id[mid]["extra"] = extra
        if extra.get("unit") == "song":
            by_id[mid]["pricing"] = {
                "input_per_1m": 0.0,
                "output_per_1m": 0.0,
                "currency": "USD",
            }
            by_id[mid]["supports_chat_completion"] = False
        specialty += 1

    # Apply shutdown dates discovered from official model sections.
    for mid, shutdown in discovered_deprecations.items():
        if mid not in by_id:
            continue
        m = by_id[mid]
        m["deprecated"] = True
        extra = m.get("extra") or {}
        extra["shutdown_date"] = shutdown
        extra["source"] = SOURCE
        m["extra"] = extra
        deprecated_n += 1

    # Flags for all google models
    for m in models:
        m["supports_google_api"] = True
        m.setdefault("supports_responses_api", False)
        m.setdefault("supports_fim", False)

    reconcile_computer_use(models)

    for model in models:
        normalize_native_endpoint(model)

    models.sort(key=lambda x: x["model_id"])
    data["models"] = models
    OUT.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if INSTALLED.parent.exists() and OUT.resolve() != INSTALLED.resolve():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if m.get("pricing") and (m["pricing"].get("input_per_1m") or 0) > 0
    )

    print(
        f"google.json: updated={updated} inserted={inserted} specialty={specialty} "
        f"deprecated_flagged={deprecated_n} total={len(models)} "
        f"(active={active}, token-priced={priced})",
        flush=True,
    )


if __name__ == "__main__":
    main()
