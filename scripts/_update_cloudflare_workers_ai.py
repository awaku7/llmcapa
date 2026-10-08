"""Refresh the Cloudflare Workers AI catalog from official documentation.

The updater discovers model IDs from Cloudflare's documentation index, then
reads each model's own task type, feature badges, model-info table, and pricing.
Unknown task types retain their source label and do not receive guessed
modalities. No Cloudflare account credentials are required for catalog refresh.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "llmcapa" / "data" / "cloudflare-workers-ai.json"
LOG = ROOT / "provider_update_log.md"
MODEL_INDEX_URL = "https://developers.cloudflare.com/workers-ai/llms.txt"
MODEL_CATALOG_URL = "https://developers.cloudflare.com/workers-ai/models/"
OPENAI_COMPAT_URL = (
    "https://developers.cloudflare.com/workers-ai/configuration/"
    "open-ai-compatibility/index.md"
)
REST_API_URL = (
    "https://developers.cloudflare.com/workers-ai/get-started/rest-api/index.md"
)
OPENAI_BASE_URL = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/v1"
REST_RUN_URL = (
    "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model_id}"
)
USER_AGENT = "llmcapa-cloudflare-catalog-updater/1.0"

# These are Cloudflare's documented task-type labels, not model IDs. Unknown
# labels are retained in `extra` and intentionally map to no guessed modality.
TASK_MODALITIES: dict[str, tuple[list[str], list[str]]] = {
    "text generation": (["text"], ["text"]),
    "text embeddings": (["text"], ["embedding"]),
    "image-to-text": (["text", "image"], ["text"]),
    "text-to-image": (["text"], ["image"]),
    "image classification": (["image"], ["text"]),
    "text classification": (["text"], ["text"]),
    "translation": (["text"], ["text"]),
    "automatic speech recognition": (["audio"], ["text"]),
    "text-to-speech": (["text"], ["audio"]),
}

_MODEL_REF_RE = re.compile(
    r"^\s*-\s+\[(?P<model_id>@cf/[^\]]+)\]"
    r"\((?P<url>https://developers\.cloudflare\.com/"
    r"workers-ai/models/[^)]+)\):\s*(?P<summary>.*)$"
)


def _fetch_text(url: str, *, timeout: int = 45) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=timeout) as response:
        return response.read(4_000_000).decode("utf-8", errors="replace")


def parse_model_index(text: str) -> list[dict[str, str]]:
    """Parse model IDs and detail-page URLs from Cloudflare's llms.txt index."""
    refs: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        match = _MODEL_REF_RE.match(line)
        if not match:
            continue
        ref = match.groupdict()
        ref["url"] = ref["url"].removesuffix("/")
        refs.setdefault(ref["model_id"].casefold(), ref)
    return sorted(refs.values(), key=lambda ref: ref["model_id"].casefold())


def parse_responses_model_slugs(text: str) -> set[str]:
    """Extract model-page slugs named in the official Responses API section."""
    heading = re.search(r"(?m)^###\s+Responses API[^\n]*\n", text)
    if not heading:
        return set()
    section = text[heading.end() :]
    next_heading = re.search(r"(?m)^###\s+", section)
    if next_heading:
        section = section[: next_heading.start()]
    return set(
        re.findall(
            r"/workers-ai/models/([^/)]+)/?(?:index\.md)?(?:[)#])",
            section,
        )
    )


def _clean_markdown(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"[`*_]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _model_info_rows(text: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2 or set(cells[0]) <= {"-", ":", " "}:
            continue
        label = _clean_markdown(cells[0]).casefold()
        value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cells[1])
        value = re.sub(r"\s+", " ", value).strip()
        if label and label not in {"model info", ""}:
            rows[label] = value
    return rows


def _parse_token_count(value: str) -> int:
    match = re.search(r"([\d,]+(?:\.\d+)?)\s*(tokens?|k|m)?\b", value, re.IGNORECASE)
    if not match:
        return 0
    amount = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    if unit == "k":
        amount *= 1_000
    elif unit == "m":
        amount *= 1_000_000
    return int(amount)


def _parse_pricing(value: str, task_type: str) -> dict[str, object] | None:
    prices = {
        direction.casefold(): float(amount.replace(",", ""))
        for amount, direction in re.findall(
            r"\$([\d,]+(?:\.\d+)?)\s+per\s+(?:1\s*)?M\s+(input|output)\s+tokens?",
            value,
            re.IGNORECASE,
        )
    }
    if "input" not in prices:
        return None
    if "output" not in prices and task_type.casefold() != "text embeddings":
        return None
    return {
        "input_per_1m": prices["input"],
        "output_per_1m": prices.get("output", 0.0),
        "currency": "USD",
    }


def _feature_tags(text: str, model_id: str) -> list[str]:
    lines = text.splitlines()
    marker = f"`{model_id}`"
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == marker) + 1
    except StopIteration:
        return []

    tags: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped:
            if tags:
                continue
            continue
        if stripped.startswith("- "):
            tags.append(_clean_markdown(stripped[2:]))
            continue
        if tags:
            break
    return tags


def _task_type(text: str) -> tuple[str, str]:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("# "):
            for candidate in lines[i + 1 : i + 8]:
                if "•" in candidate:
                    task, author = candidate.split("•", 1)
                    return _clean_markdown(task), _clean_markdown(author)
                if "Copy as Markdown" in candidate:
                    break
    return "", ""


def _reasoning_effort_values(value: str) -> list[str] | None:
    values = [_clean_markdown(item).lower() for item in re.findall(r"`([^`]+)`", value)]
    values = list(dict.fromkeys(value for value in values if value))
    return values or None


def parse_model_page(
    model_ref: dict[str, str],
    text: str,
    *,
    responses_model_slugs: set[str],
    checked_at: str,
) -> dict[str, object]:
    """Convert one official model page into a conservative Capability record."""
    model_id = model_ref["model_id"]
    url_parts = model_ref["url"].rstrip("/").split("/")
    slug = url_parts[-2] if url_parts[-1] == "index.md" else url_parts[-1]

    model_id_match = re.search(r"(?m)^`(@cf/[^`]+)`\s*$", text)
    if model_id_match and model_id_match.group(1) != model_id:
        raise ValueError(
            f"Model ID mismatch for {model_ref['url']}: "
            f"index={model_id!r}, detail={model_id_match.group(1)!r}"
        )

    title_match = re.search(r"(?m)^title:\s*(.+?)\s*$", text)
    title = _clean_markdown(title_match.group(1)) if title_match else slug
    description_match = re.search(r"(?m)^description:\s*(.+?)\s*$", text)
    description = (
        _clean_markdown(description_match.group(1))
        if description_match
        else model_ref.get("summary", "")
    )
    task_type, author = _task_type(text)
    normalized_task = task_type.casefold()
    input_modalities, output_modalities = TASK_MODALITIES.get(normalized_task, ([], []))
    input_modalities = list(input_modalities)
    output_modalities = list(output_modalities)

    tags = _feature_tags(text, model_id)
    normalized_tags = {tag.casefold() for tag in tags}
    if "vision" in normalized_tags and "image" not in input_modalities:
        input_modalities.append("image")
    if "video" in normalized_tags and "video" not in input_modalities:
        input_modalities.append("video")

    info = _model_info_rows(text)
    context_row = next(
        (value for key, value in info.items() if "context window" in key), ""
    )
    max_output_row = next(
        (
            value
            for key, value in info.items()
            if "max output" in key or "max completion" in key
        ),
        "",
    )
    reasoning_row = next(
        (value for key, value in info.items() if key == "reasoning"), ""
    )
    reasoning_values = _reasoning_effort_values(reasoning_row)
    if "reasoning" in normalized_tags and reasoning_row and not reasoning_values:
        reasoning_values = None

    chat_compatible = (
        normalized_task == "text generation" and "/v1/chat/completions" in text
    )
    embeddings_compatible = (
        "embedding" in output_modalities and "/v1/embeddings" in text
    )
    responses_compatible = slug in responses_model_slugs
    streaming = bool(chat_compatible and re.search(r"(?im)^Streaming\s*[—-]", text))

    pricing_row = next(
        (value for key, value in info.items() if "unit pricing" in key), ""
    )
    pricing = _parse_pricing(pricing_row, task_type)
    terms_row = next(
        (value for key, value in info.items() if "terms and license" in key), ""
    )
    terms_url = ""
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if (
            len(cells) >= 2
            and "terms and license" in _clean_markdown(cells[0]).casefold()
        ):
            link = re.search(r"\[[^\]]+\]\((https?://[^)]+)\)", cells[1])
            if link:
                terms_url = link.group(1)
            break

    endpoints: list[dict[str, str]] = []
    if chat_compatible:
        endpoints.append(
            {
                "path": "/chat/completions",
                "protocol": "openai-compatible",
                "base_url": OPENAI_BASE_URL,
                "auth": "bearer",
                "source": OPENAI_COMPAT_URL,
            }
        )
    if embeddings_compatible:
        endpoints.append(
            {
                "path": "/embeddings",
                "protocol": "openai-compatible",
                "base_url": OPENAI_BASE_URL,
                "auth": "bearer",
                "source": OPENAI_COMPAT_URL,
            }
        )
    if responses_compatible:
        endpoints.append(
            {
                "path": "/responses",
                "protocol": "openai-compatible",
                "base_url": OPENAI_BASE_URL,
                "auth": "bearer",
                "source": OPENAI_COMPAT_URL,
            }
        )

    extra: dict[str, object] = {
        "official_source": MODEL_CATALOG_URL,
        "official_model_source": model_ref["url"],
        "official_api_source": OPENAI_COMPAT_URL,
        "official_catalog_checked_at": checked_at,
        "description": description,
        "cloudflare_task_type": task_type,
        "cloudflare_author": author,
        "cloudflare_tags": tags,
        "cloudflare_model_id": model_id,
        "cloudflare_rest_api_source": REST_API_URL,
        "cloudflare_rest_run_url_template": REST_RUN_URL,
        "openai_compatible_base_url_template": OPENAI_BASE_URL,
        "batch_available": "batch" in normalized_tags
        or info.get("batch", "").casefold() == "yes",
        "endpoints": endpoints,
    }
    if pricing_row:
        extra["official_unit_pricing"] = pricing_row
    if terms_row:
        extra["terms_and_license"] = terms_row
    if terms_url:
        extra["terms_and_license_url"] = terms_url
    if "paid access required" in text.casefold():
        extra["paid_access_required"] = True
    if not task_type:
        extra["task_type_unavailable"] = True

    record: dict[str, object] = {
        "provider": "cloudflare-workers-ai",
        "model_id": model_id,
        "display_name": title,
        "context_window": _parse_token_count(context_row),
        "max_output_tokens": _parse_token_count(max_output_row),
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": "function calling" in normalized_tags
        or info.get("function calling", "").casefold() == "yes",
        "supports_json_mode": (
            True if "structured outputs" in normalized_tags else None
        ),
        "supports_streaming": streaming,
        "supports_vision": "image" in input_modalities,
        "supports_reasoning": "reasoning" in normalized_tags
        or bool(reasoning_row and reasoning_row.casefold() not in {"no", "none"}),
        "supports_chat_completion": chat_compatible,
        "supports_responses_api": responses_compatible,
        "supports_reasoning_effort": bool(reasoning_values),
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "deprecated": False,
        "aliases": [],
        "license_type": "api",
        "pricing": pricing,
        "extra": extra,
    }
    if reasoning_values:
        record["reasoning_effort_values"] = reasoning_values
    return enrich_clef_decision(record)


CLEF_INPUT_PRICES = {
    "@cf/cloudflare/clef": 0.24,
    "@cf/cloudflare/clef-flash": 0.09,
}


def enrich_clef_decision(record: dict[str, object]) -> dict[str, object]:
    """Apply official Clef decision metadata to the generic Workers AI parser.

    The documentation labels Clef as 'Text Generation', but its Workers AI
    endpoint returns typed decisions, not generated chat text. Its published
    price is input-only, which the general text-model parser cannot represent.
    """
    model_id = str(record.get("model_id") or "")
    if model_id not in CLEF_INPUT_PRICES:
        return record

    selector = model_id.rsplit("/", 1)[-1]
    official_model_source = (
        f"https://developers.cloudflare.com/workers-ai/models/{selector}/"
    )
    extra = dict(record.get("extra") or {})
    # The generic parser adds a Chat Completions base URL for every model;
    # Clef's typed-decision endpoint is not OpenAI chat compatible.
    extra.pop("openai_compatible_base_url_template", None)
    extra.update(
        official_model_source=official_model_source,
        official_api_source=official_model_source,
        cloudflare_model_id=model_id,
        cloudflare_model_selector=selector,
        cloudflare_rest_run_url_template=REST_RUN_URL,
        endpoints=[
            {
                "path": f"/ai/run/{model_id}",
                "protocol": "systemone-compatible",
                "url_template": REST_RUN_URL.replace("{model_id}", model_id),
                "auth": "bearer",
                "source": official_model_source,
            }
        ],
        open_weights_url=f"https://huggingface.co/Cloudflare/{selector}",
        open_weights_license="Apache-2.0",
        parameters_billion=27 if selector == "clef" else 9,
        max_images=4,
        images_embedded_only=True,
        image_formats=["png", "jpeg", "webp"],
        video_input_note=(
            "The model card mentions video input; the Workers AI request "
            "schema documents images but does not document a videos field."
        ),
    )
    record.update(
        context_window=65_536,
        max_output_tokens=0,
        input_modalities=["text", "image"],
        output_modalities=["decision"],
        supports_vision=True,
        supports_function_calling=False,
        supports_json_mode=False,
        supports_chat_completion=False,
        supports_responses_api=False,
        supports_reasoning=False,
        supports_reasoning_effort=False,
        supports_streaming=False,
        supports_json_schema=False,
        license_type="api",
        aliases=[selector, f"cloudflare/{selector}"],
        pricing={
            "input_per_1m": CLEF_INPUT_PRICES[model_id],
            "output_per_1m": 0.0,
            "currency": "USD",
        },
        decision={
            "decision": True,
            "question_kinds": ["noul", "choice", "score"],
            "answer_fields": [
                "noul",
                "choice",
                "score",
                "probabilities",
                "confidence",
                "legend",
            ],
            "returns_probabilities": True,
            "returns_confidence": True,
            "parallel_questions": True,
            "free_form_text": False,
            "type_errors_possible": False,
            "state_shapes": ["string", "json_object", "text_array"],
            "max_total_tokens": 65_536,
            "max_questions": 64,
            "output_token_billing": False,
            "endpoints": [REST_RUN_URL.replace("{model_id}", model_id)],
            "source_url": official_model_source,
            "checked_at": extra.get("official_catalog_checked_at"),
            "status": "documented",
            "extra": {
                "endpoint_protocol": "systemone-compatible",
                "request_model": selector,
                "request_fields": ["model", "state", "questions", "images"],
                "max_images": 4,
                "not_openai_chat_completions": True,
            },
        },
        extra=extra,
    )
    return record


def fetch_catalog() -> list[dict[str, object]]:
    index_text = _fetch_text(MODEL_INDEX_URL)
    model_refs = parse_model_index(index_text)
    if not model_refs:
        raise RuntimeError(
            "No Workers AI model entries found in the official docs index"
        )

    compatibility_text = _fetch_text(OPENAI_COMPAT_URL)
    response_slugs = parse_responses_model_slugs(compatibility_text)
    checked_at = datetime.now(timezone.utc).date().isoformat()

    def fetch_one(ref: dict[str, str]) -> dict[str, object]:
        return parse_model_page(
            ref,
            _fetch_text(ref["url"]),
            responses_model_slugs=response_slugs,
            checked_at=checked_at,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        records = list(executor.map(fetch_one, model_refs))

    model_ids = [str(record["model_id"]).casefold() for record in records]
    if len(model_ids) != len(set(model_ids)):
        raise RuntimeError("Duplicate Cloudflare Workers AI model IDs in documentation")
    return sorted(records, key=lambda record: str(record["model_id"]).casefold())


def update_catalog() -> list[dict[str, object]]:
    models = fetch_catalog()
    OUTPUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    task_types = sorted(
        {
            str((model.get("extra") or {}).get("cloudflare_task_type") or "(missing)")
            for model in models
        }
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Cloudflare Workers AI official catalog refresh ({datetime.now(timezone.utc).date()})\n\n"
        + f"- Model source: {MODEL_INDEX_URL}\n"
        + f"- OpenAI compatibility: {OPENAI_COMPAT_URL}\n"
        + f"- Models parsed: {len(models)}\n"
        + f"- Task types: {', '.join(task_types)}\n"
        + "- Model IDs and per-model fields were read from the official index and detail pages; unlisted values remain unknown.\n",
        encoding="utf-8",
    )
    print(f"cloudflare-workers-ai.json: {len(models)} official model pages")
    return models


def main() -> None:
    update_catalog()


if __name__ == "__main__":
    main()
