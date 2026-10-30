"""Build/refresh amazon.json from AWS Bedrock model cards and Nova pricing.

The model inventory is read from AWS's Models at a glance page and its linked
model cards, so all officially listed Bedrock publishers are included.

Nova pricing sources (official AWS pages and metered unit map):
- https://aws.amazon.com/bedrock/pricing/ (Amazon → Amazon Nova)
- https://aws.amazon.com/nova/pricing/
- https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/bedrock/USD/current/bedrock.json
- _scratch_amazon_nova_pricing_live.html

Primary pricing: US East (N. Virginia) On-Demand Standard.
Nova 2 text models: Global Cross-Region Inference (CRI) as primary;
geo/in-region rates stored in extra.
Cache read = 75% less than on-demand input (official).
"""

from __future__ import annotations

import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

from _computer_use_metadata import anthropic_computer_use_capability

try:
    from scripts._scrape_amazon import fetch_nova_prices as _fetch_nova_prices
except ModuleNotFoundError:
    try:
        from _scrape_amazon import fetch_nova_prices as _fetch_nova_prices
    except ModuleNotFoundError:
        _fetch_nova_prices = None

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "amazon.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "amazon.json"
)
SOURCE_BEDROCK = "https://aws.amazon.com/bedrock/pricing/"
SOURCE_NOVA = "https://aws.amazon.com/nova/pricing/"
MODEL_CARDS_URL = "https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.md"
BEDROCK_DOCS_BASE = "https://docs.aws.amazon.com/bedrock/latest/userguide/"
BEDROCK_RUNTIME_URL = "https://bedrock-runtime.{region}.amazonaws.com"
BEDROCK_MANTLE_URL = "https://bedrock-mantle.{region}.api.aws"
ANTHROPIC_DATA = WORKDIR / "src" / "llmcapa" / "data" / "anthropic.json"
BEDROCK_CLAUDE_MODELS = {
    "anthropic.claude-opus-5-5": ("claude-opus-5-5", "anthropic-claude-opus-5-5"),
    "anthropic.claude-sonnet-5-5": ("claude-sonnet-5-5", "anthropic-claude-sonnet-5-5"),
    "anthropic.claude-opus-5": ("claude-opus-5", "anthropic-claude-opus-5"),
    "anthropic.claude-sonnet-5": ("claude-sonnet-5", "anthropic-claude-sonnet-5"),
    "anthropic.claude-opus-4-8": ("claude-opus-4-8", "anthropic-claude-opus-4-8"),
    "anthropic.claude-opus-4-7": ("claude-opus-4-7", "anthropic-claude-opus-4-7"),
    "anthropic.claude-opus-4-6-v1": ("claude-opus-4-6", "anthropic-claude-opus-4-6"),
    "anthropic.claude-sonnet-4-6": ("claude-sonnet-4-6", "anthropic-claude-sonnet-4-6"),
    "anthropic.claude-opus-4-5-20251101-v1:0": (
        "claude-opus-4-5",
        "anthropic-claude-opus-4-5",
    ),
    "anthropic.claude-sonnet-4-5-20250929-v1:0": (
        "claude-sonnet-4-5",
        "anthropic-claude-sonnet-4-5",
    ),
    "anthropic.claude-haiku-4-5-20251001-v1:0": (
        "claude-haiku-4-5",
        "anthropic-claude-haiku-4-5",
    ),
}
SOURCE_API = (
    "https://b0.p.awsstatic.com/pricing/2.0/meteredUnitMaps/"
    "bedrock/USD/current/bedrock.json"
)
REGION_NOTE = "US East (N. Virginia) on-demand standard"
NOVA_PRICING_MODE = "live"


def fetch_text(url: str) -> str:
    """Fetch a bounded UTF-8 document from an official AWS source."""
    request = Request(url, headers={"User-Agent": "llmcapa-bedrock-updater/1.0"})
    with urlopen(request, timeout=30) as response:
        content = response.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise RuntimeError(f"AWS documentation response is too large: {url}")
    return content.decode("utf-8")


def discover_model_card_urls(index_markdown: str) -> list[str]:
    """Return every model-card link in AWS's official models-at-a-glance page."""
    links = re.findall(
        r"\[[^\]]+\]\((model-card-[^)#]+\.md)(?:#[^)]*)?\)",
        index_markdown,
        flags=re.IGNORECASE,
    )
    return list(dict.fromkeys(BEDROCK_DOCS_BASE + link for link in links))


def _clean_markdown(value: str) -> str:
    value = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    return re.sub(r"[*`_]", "", value).strip()


def _section(markdown: str, title: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(title)}\s*$\n(.*?)(?=^##\s+|\Z)",
        markdown,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    return match.group(1) if match else ""


def _markdown_tables(section: str) -> list[tuple[list[str], list[list[str]]]]:
    """Extract simple pipe tables as normalized headers and raw cell values."""
    lines = section.splitlines()
    result = []
    index = 0
    while index < len(lines) - 1:
        if not lines[index].lstrip().startswith("|") or not re.search(
            r"\|\s*:?-{2,}", lines[index + 1]
        ):
            index += 1
            continue
        headers = [
            _clean_markdown(cell) for cell in lines[index].strip().strip("|").split("|")
        ]
        rows: list[list[str]] = []
        index += 2
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
            if len(row) == len(headers):
                rows.append(row)
            index += 1
        result.append((headers, rows))
    return result


def _supported(value: str) -> bool | None:
    """Interpret AWS's yes/no icon markup without treating 'not-supported' as yes."""
    lowered = value.lower()
    if "icon-no" in lowered or "not-supported" in lowered or "not supported" in lowered:
        return False
    if "icon-yes" in lowered or re.search(r"\bsupported\b", lowered):
        return True
    return None


def _model_ids(cell: str) -> list[str]:
    """Read model identifiers from code-formatted AWS documentation cells."""
    values = re.findall(r"`([^`]+)`", cell)
    if not values:
        values = re.findall(
            r"\b(?:[a-z][a-z0-9-]*\.)+[a-z0-9][a-z0-9.:-]*\b", cell, re.IGNORECASE
        )
    return [
        value.strip()
        for value in values
        if value.strip().lower() not in {"n/a", "not supported", "none"}
    ]


def _parse_programmatic_access(markdown: str) -> tuple[str, list[str], dict[str, str]]:
    section = _section(markdown, "Programmatic Access") or _section(
        markdown, "Call the model"
    )
    aliases: list[str] = []
    endpoint_urls: dict[str, str] = {}
    canonical = ""
    for headers, rows in _markdown_tables(section):
        normalized = [header.lower() for header in headers]
        if not any("model id" in header for header in normalized):
            continue
        id_column = next(
            i for i, header in enumerate(normalized) if "model id" in header
        )
        endpoint_column = next(
            (i for i, header in enumerate(normalized) if header == "endpoint"), None
        )
        url_column = next(
            (i for i, header in enumerate(normalized) if "endpoint url" in header), None
        )
        alias_columns = [
            i
            for i, header in enumerate(normalized)
            if "inference id" in header or "profile id" in header
        ]
        for row in rows:
            if id_column >= len(row):
                continue
            ids = _model_ids(row[id_column])
            endpoint = (
                _clean_markdown(row[endpoint_column]).lower()
                if endpoint_column is not None
                else ""
            )
            if ids and (not canonical or endpoint == "bedrock-runtime"):
                canonical = ids[0]
            for value in ids[1:]:
                if value not in aliases:
                    aliases.append(value)
            for column in alias_columns:
                for value in _model_ids(row[column]):
                    if value not in aliases:
                        aliases.append(value)
            if endpoint and url_column is not None and url_column < len(row):
                urls = re.findall(r"https?://[^\s|<>]+", row[url_column])
                if urls:
                    endpoint_urls[endpoint] = urls[0].rstrip(".,`")
    return canonical, aliases, endpoint_urls


def _parse_modalities(markdown: str) -> tuple[list[str], list[str]]:
    for headers, rows in _markdown_tables(markdown):
        normalized = [header.lower() for header in headers]
        if not any("input modalities" in item for item in normalized) or not any(
            "output modalities" in item for item in normalized
        ):
            continue
        input_index = next(
            i for i, value in enumerate(normalized) if "input modalities" in value
        )
        output_index = next(
            i for i, value in enumerate(normalized) if "output modalities" in value
        )
        inputs: list[str] = []
        outputs: list[str] = []
        for row in rows:
            cells = ((row[input_index], inputs), (row[output_index], outputs))
            for cell, target in cells:
                if _supported(cell) is not True:
                    continue
                label = _clean_markdown(cell).lower()
                match = re.search(
                    r"\b(audio|embedding|image|speech|text|video)\b", label
                )
                if match and match.group(1) not in target:
                    target.append(match.group(1))
        return inputs, outputs
    return [], []


def _parse_api_support(markdown: str) -> dict[str, bool]:
    section = _section(markdown, "Endpoints and APIs supported")
    result: dict[str, bool] = {}
    lines = section.splitlines()
    for index, line in enumerate(lines):
        heading = re.search(
            r"APIs supported on.*?`(bedrock-[a-z-]+)`", line, re.IGNORECASE
        )
        if not heading:
            continue
        endpoint_tables = _markdown_tables("\n".join(lines[index + 1 :]))
        if not endpoint_tables:
            continue
        headers, rows = endpoint_tables[0]
        for row in rows[:1]:
            for header, value in zip(headers, row):
                key = _clean_markdown(header).lower()
                if key in {
                    "messages",
                    "responses",
                    "chat completions",
                    "converse",
                    "invoke",
                }:
                    result[f"{heading.group(1).lower()}:{key}"] = (
                        _supported(value) is True
                    )
    return result


def _parse_endpoint_support(markdown: str) -> set[str]:
    section = _section(markdown, "Endpoints and APIs supported")
    for headers, rows in _markdown_tables(section):
        normalized = [header.lower() for header in headers]
        if "endpoint" not in normalized or "supported" not in normalized:
            continue
        endpoint_index = normalized.index("endpoint")
        supported_index = normalized.index("supported")
        return {
            _clean_markdown(row[endpoint_index]).lower()
            for row in rows
            if _supported(row[supported_index]) is True
        }
    return set()


def _token_count(markdown: str, label: str) -> int:
    match = re.search(
        rf"\*\*{re.escape(label)}:\*\*\s*([\d,.]+)\s*([KMB])?\s*(?:tokens?)?",
        markdown,
        flags=re.IGNORECASE,
    )
    if not match:
        return 0
    value = float(match.group(1).replace(",", ""))
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
        (match.group(2) or "").lower(), 1
    )
    return int(value * multiplier)


def _explicit_feature(markdown: str, pattern: str) -> bool:
    for line in markdown.splitlines():
        for segment in re.split(r"<br\s*/?>|\|", line, flags=re.IGNORECASE):
            if not re.search(pattern, segment, re.IGNORECASE):
                continue
            status = _supported(segment)
            if status is True:
                return True
            if status is False:
                continue
            positive = re.search(
                r"\b(supports?|supported|enabled|available|yes)\b",
                segment,
                re.IGNORECASE,
            )
            negative = re.search(
                r"\b(does not|not supported|unsupported|no longer)\b",
                segment,
                re.IGNORECASE,
            )
            if positive and not negative:
                return True
    return False


def parse_bedrock_model_card(markdown: str, source_url: str) -> dict | None:
    """Normalize one AWS model card into an Amazon/Bedrock catalog record."""
    model_id, aliases, endpoint_urls = _parse_programmatic_access(markdown)
    if not model_id:
        return None
    title_match = re.search(r"^#\s+(.+?)\s*$", markdown, re.MULTILINE)
    display = _clean_markdown(title_match.group(1)) if title_match else model_id
    publisher_match = re.search(
        r"^##\s+.*?\s([\w .&/+()-]+?)\s+[—–-]\s+.+$",
        markdown,
        re.MULTILINE,
    )
    publisher = _clean_markdown(publisher_match.group(1)) if publisher_match else ""
    input_modalities, output_modalities = _parse_modalities(markdown)
    api_support = _parse_api_support(markdown)
    endpoint_support = _parse_endpoint_support(markdown) or {"bedrock-runtime"}

    endpoints = []
    if "bedrock-runtime" in endpoint_support:
        endpoints.append(
            {
                "base_url": BEDROCK_RUNTIME_URL,
                "protocol": "aws-bedrock",
                "auth": "sigv4",
                "source": source_url,
            }
        )
    if "bedrock-mantle" in endpoint_support:
        endpoints.append(
            {
                "base_url": endpoint_urls.get("bedrock-mantle", BEDROCK_MANTLE_URL),
                "protocol": "aws-bedrock-mantle",
                "auth": "bearer",
                "source": source_url,
            }
        )

    modalities = input_modalities or ["text"]
    output_modalities = output_modalities or ["text"]
    knowledge = re.search(
        r"\*\*Knowledge cutoff:\*\*\s*([^\n]+)", markdown, re.IGNORECASE
    )
    lifecycle = re.search(
        r"\*\*Model lifecycle:\*\*\s*([^\n]+)", markdown, re.IGNORECASE
    )
    reasoning_line = re.search(
        r"\*\*Reasoning:\*\*\s*([^\n]+)", markdown, re.IGNORECASE
    )
    reasoning_effort = bool(
        re.search(
            r"^\s*\*\*Reasoning effort\*\*",
            markdown,
            re.IGNORECASE | re.MULTILINE,
        )
        or _explicit_feature(markdown, r"Reasoning effort|effort level configurable")
    )
    reasoning = bool(
        (reasoning_line and _supported(reasoning_line.group(1)) is True)
        or reasoning_effort
    )
    record = base(
        model_id=model_id,
        display=display,
        ctx=_token_count(markdown, "Context window"),
        max_out=_token_count(markdown, "Max output tokens"),
        pricing=None,
        aliases=aliases,
        knowledge_cutoff=_clean_markdown(knowledge.group(1)) if knowledge else None,
        input_modalities=modalities,
        output_modalities=output_modalities,
        vision="image" in modalities,
        reasoning=reasoning,
        function_calling=_explicit_feature(
            markdown, r"tool use|tool calling|function calling|client-side tools?"
        ),
        streaming=_explicit_feature(markdown, r"Response streaming"),
        json_mode=_explicit_feature(
            markdown, r"Structured outputs?|JSON Schema output|JSON mode"
        ),
        chat=any(
            value
            for key, value in api_support.items()
            if key.endswith((":messages", ":chat completions", ":converse"))
        ),
        include_nova_pricing_sources=False,
        extra={
            "source": source_url,
            "bedrock_model_provider": publisher or None,
            "endpoints": endpoints,
            "supported_bedrock_endpoints": sorted(endpoint_support),
        },
    )
    # Keep only model/profile IDs explicitly listed by AWS, not synthetic IDs
    # from another provider's routing convention.
    record["aliases"] = aliases
    record["deprecated"] = bool(
        lifecycle
        and _clean_markdown(lifecycle.group(1)).lower()
        in {"legacy", "deprecated", "end of life"}
    )
    record["supports_reasoning_effort"] = reasoning_effort
    record["supports_responses_api"] = any(
        value for key, value in api_support.items() if key.endswith(":responses")
    )
    record["supports_anthropic_api"] = any(
        value for key, value in api_support.items() if key.endswith(":messages")
    )
    return record


def fetch_bedrock_models() -> list[dict]:
    """Fetch all model cards linked from AWS's official model inventory."""
    index = fetch_text(MODEL_CARDS_URL)
    urls = discover_model_card_urls(index)
    if not urls:
        raise RuntimeError("AWS Bedrock model inventory contained no model cards")
    models: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_text, url): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                record = parse_bedrock_model_card(future.result(), url)
            except (OSError, ValueError, RuntimeError) as exc:
                errors.append(f"{url}: {exc}")
                continue
            if record is not None:
                models.append(record)
    if not models:
        detail = "; ".join(errors[:3])
        raise RuntimeError(f"Could not parse any AWS Bedrock model cards. {detail}")
    if errors:
        print(
            "AWS Bedrock model cards skipped after fetch/parse errors: "
            f"{len(errors)}"
        )
    return sorted(models, key=lambda item: item["model_id"].lower())


def fetch_nova_prices() -> dict[str, dict[str, float]]:
    """Use the official Nova scraper, or reuse bundled pricing if absent.

    The repository snapshot may not include the optional legacy pricing
    scraper. In that case, reuse the last bundled Nova prices so catalog
    reconciliation remains runnable without claiming a live price refresh.
    """
    global NOVA_PRICING_MODE
    if _fetch_nova_prices is not None:
        NOVA_PRICING_MODE = "live"
        return _fetch_nova_prices()
    data = json.loads(OUT.read_text(encoding="utf-8"))
    cached = {}
    for model in data.get("models", []):
        model_id = str(model.get("model_id", ""))
        pricing = model.get("pricing") or {}
        if not model_id.startswith("nova-"):
            continue
        if pricing.get("input_per_1m") is None or pricing.get("output_per_1m") is None:
            continue
        cached[model_id] = {
            "input": pricing["input_per_1m"],
            "output": pricing["output_per_1m"],
        }
    if not cached:
        raise RuntimeError(
            "Nova price scraper unavailable and no bundled prices to reuse"
        )
    NOVA_PRICING_MODE = "bundled-cache"
    return cached


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    pricing: dict | None,
    extra: dict | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    knowledge_cutoff: str | None = None,
    input_modalities: list[str] | None = None,
    output_modalities: list[str] | None = None,
    vision: bool = False,
    reasoning: bool = False,
    function_calling: bool = True,
    streaming: bool = True,
    json_mode: bool = False,
    chat: bool = True,
    include_nova_pricing_sources: bool = True,
) -> dict:
    aliases = list(aliases or [])
    # Native catalog: Bedrock harness alias amazon.<id>:0 only.
    # Route-qualified IDs such as amazon/<id> belong to the
    # openrouter catalog and must not be added as native aliases.
    bare = model_id
    bare = bare.removeprefix("amazon/")
    br_id = f"amazon.{bare}:0" if not bare.startswith("amazon.") else bare
    # also bare without version suffix variants handled by caller
    for a in (br_id,):
        if a not in aliases and a != model_id:
            aliases.append(a)

    in_mod = list(input_modalities or (["text", "image"] if vision else ["text"]))
    out_mod = list(output_modalities or ["text"])

    row: dict = {
        "provider": "amazon",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": in_mod,
        "output_modalities": out_mod,
        "supports_function_calling": function_calling,
        "supports_json_mode": json_mode,
        "supports_streaming": streaming,
        "supports_vision": vision or ("image" in in_mod),
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": False,
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": knowledge_cutoff,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": "api",
    }
    if pricing is not None:
        row["pricing"] = {
            "input_per_1m": pricing.get("input"),
            "output_per_1m": pricing.get("output"),
            "currency": "USD",
        }
        # specialty unit prices (image/sec) may live only in extra
        if (
            pricing.get("input") is None
            and pricing.get("output") is None
            and "unit" in (extra or {})
        ):
            row["pricing"] = {"currency": "USD"}
    else:
        row["pricing"] = None

    ex = {"source": SOURCE_BEDROCK}
    if include_nova_pricing_sources:
        ex.update(
            {
                "nova_pricing": SOURCE_NOVA,
                "price_api": SOURCE_API,
                "region": REGION_NOTE,
            }
        )
    ex.update(extra or {})
    row["extra"] = ex
    return row


def text_extra(
    *,
    cache_hit: float | None = None,
    batch_in: float | None = None,
    batch_out: float | None = None,
    geo_in: float | None = None,
    geo_out: float | None = None,
    latency_opt_in: float | None = None,
    latency_opt_out: float | None = None,
    notes: dict | None = None,
) -> dict:
    e: dict = {}
    if cache_hit is not None:
        e["cache_hit_per_1m"] = cache_hit
        e["cache_hit_note"] = "75% less than on-demand input (official)"
    if batch_in is not None:
        e["batch_input_per_1m"] = batch_in
    if batch_out is not None:
        e["batch_output_per_1m"] = batch_out
    if geo_in is not None:
        e["geo_input_per_1m"] = geo_in
    if geo_out is not None:
        e["geo_output_per_1m"] = geo_out
    if latency_opt_in is not None:
        e["latency_optimized_input_per_1m"] = latency_opt_in
    if latency_opt_out is not None:
        e["latency_optimized_output_per_1m"] = latency_opt_out
    if notes:
        e.update(notes)
    return e


def add_bedrock_claude_models(models: list[dict]) -> int:
    """Add Claude models whose AWS model cards explicitly expose Computer use."""
    anthropic_models = {
        model.get("model_id"): model
        for model in json.loads(ANTHROPIC_DATA.read_text(encoding="utf-8")).get(
            "models", []
        )
    }
    by_id = {model.get("model_id"): model for model in models}
    inserted = 0
    for bedrock_id, (anthropic_id, card_slug) in BEDROCK_CLAUDE_MODELS.items():
        if bedrock_id in by_id:
            continue
        source = anthropic_models.get(anthropic_id)
        if source is None:
            continue
        card_url = (
            "https://docs.aws.amazon.com/bedrock/latest/userguide/"
            f"model-card-{card_slug}.html"
        )
        model = base(
            model_id=bedrock_id,
            display=(
                f"Anthropic {source.get('display_name', anthropic_id)} "
                "(Amazon Bedrock)"
            ),
            ctx=source.get("context_window") or 0,
            max_out=source.get("max_output_tokens") or 0,
            pricing=None,
            input_modalities=source.get("input_modalities") or ["text"],
            output_modalities=source.get("output_modalities") or ["text"],
            vision=source.get("supports_vision", False),
            reasoning=source.get("supports_reasoning", False),
            function_calling=source.get("supports_function_calling", True),
            extra={
                "bedrock_model_family": "anthropic-claude",
                "source": card_url,
                "computer_use_note": (
                    "Computer Use is documented on this " "Bedrock model card."
                ),
            },
            include_nova_pricing_sources=False,
        )
        model["display_name"] = (
            f"Anthropic {source.get('display_name', anthropic_id)} (Amazon Bedrock)"
        )
        model["supports_anthropic_api"] = False
        model["extra"]["endpoints"] = [
            {
                "base_url": "https://bedrock-runtime.{region}.amazonaws.com",
                "protocol": "aws-bedrock",
                "auth": "sigv4",
                "source": card_url,
            }
        ]
        capability = anthropic_computer_use_capability(bedrock_id, "amazon")
        if capability is None:
            continue
        capability["source_url"] = card_url
        model["computer_use"] = capability
        models.append(model)
        by_id[bedrock_id] = model
        inserted += 1
    return inserted


def _merge_official_model(existing: dict, official: dict) -> dict:
    """Refresh documented fields while retaining curated/pricing metadata."""
    merged = dict(existing)
    refresh_fields = {
        "provider",
        "display_name",
        "context_window",
        "max_output_tokens",
        "input_modalities",
        "output_modalities",
        "supports_function_calling",
        "supports_json_mode",
        "supports_streaming",
        "supports_vision",
        "supports_reasoning",
        "supports_chat_completion",
        "supports_responses_api",
        "supports_reasoning_effort",
        "supports_thinking_budget",
        "supports_anthropic_api",
        "knowledge_cutoff",
        "deprecated",
        "license_type",
    }
    conservative_flags = {
        "supports_function_calling",
        "supports_json_mode",
        "supports_streaming",
        "supports_reasoning",
        "supports_chat_completion",
        "supports_responses_api",
        "supports_reasoning_effort",
        "supports_anthropic_api",
    }
    for key in refresh_fields:
        if key not in official:
            continue
        if (
            key in conservative_flags
            and official[key] is False
            and merged.get(key) is True
        ):
            continue
        merged[key] = official[key]
    aliases = list(merged.get("aliases") or [])
    for alias in official.get("aliases") or []:
        if alias not in aliases and alias != official.get("model_id"):
            aliases.append(alias)
    merged["aliases"] = aliases
    merged_extra = dict(merged.get("extra") or {})
    merged_extra.update(official.get("extra") or {})
    merged["extra"] = merged_extra
    return merged


def build(
    nova_prices: dict[str, dict[str, float]],
    bedrock_models: list[dict] | None = None,
) -> list[dict]:
    """Refresh AWS's full model-card inventory and Nova pricing.

    The previous catalog is retained as a compatibility source for legacy
    records. AWS's official Models at a glance index is the source of truth
    for the currently documented Bedrock model inventory.
    """
    if not nova_prices:
        raise RuntimeError("official AWS pricing returned no Nova models")
    try:
        current = json.loads(OUT.read_text(encoding="utf-8"))
        models = [dict(model) for model in current.get("models", [])]
    except (OSError, json.JSONDecodeError):
        models = []

    # AWS's current model card uses the versioned programmatic ID.
    for model in models:
        if model.get("model_id") == "anthropic.claude-opus-4-6":
            model["model_id"] = "anthropic.claude-opus-4-6-v1"
            model["computer_use"] = anthropic_computer_use_capability(
                model["model_id"], "amazon"
            )
    bedrock_claude_inserted = add_bedrock_claude_models(models)

    by_id = {str(model.get("model_id", "")): model for model in models}
    for official in bedrock_models or []:
        model_id = str(official.get("model_id", ""))
        if not model_id:
            continue
        existing = by_id.get(model_id)
        if existing is None:
            model = dict(official)
            models.append(model)
            by_id[model_id] = model
        else:
            model = _merge_official_model(existing, official)
            index = models.index(existing)
            models[index] = model
            by_id[model_id] = model

    by_id = {str(model.get("model_id", "")): model for model in models}
    for model_id, rate in nova_prices.items():
        model = by_id.get(model_id)
        if model is None:
            model = base(
                model_id=model_id,
                display=model_id.replace("-", " ").title(),
                ctx=0,
                max_out=0,
                pricing=rate,
                extra={
                    "catalog_metadata_status": "official price only; limits unknown"
                },
            )
            models.append(model)
            by_id[model_id] = model
        else:
            model["pricing"] = {
                "input_per_1m": rate.get("input"),
                "output_per_1m": rate.get("output"),
                "currency": "USD",
            }
            model.setdefault("extra", {})["pricing_source"] = SOURCE_NOVA
    # Bedrock Claude entries are carried forward from the curated model
    # catalog. Reconcile their Computer Use beta/tool versions against the
    # current Anthropic/AWS compatibility table on every refresh.
    for model in models:
        computer_use = anthropic_computer_use_capability(
            model.get("model_id", ""), "amazon"
        )
        if computer_use is not None:
            model["computer_use"] = computer_use
        elif (model.get("computer_use") or {}).get("provider") == "amazon":
            model.pop("computer_use", None)
    print(f"Bedrock Claude Computer Use models inserted={bedrock_claude_inserted}")
    return dedupe_model_ids(models)


def dedupe_model_ids(models: list[dict]) -> list[dict]:
    by_id: dict[str, dict] = {}
    order: list[str] = []
    for m in models:
        mid = m["model_id"]
        if mid not in by_id:
            by_id[mid] = m
            order.append(mid)
            continue
        existing = by_id[mid]
        seen = set(existing.get("aliases") or [])
        for a in m.get("aliases") or []:
            if a not in seen:
                existing.setdefault("aliases", []).append(a)
                seen.add(a)
    for mid, m in by_id.items():
        aliases: list[str] = []
        seen: set[str] = set()
        for a in m.get("aliases") or []:
            if a == mid or a in seen:
                continue
            if a.startswith("amazon/amazon/"):
                continue
            aliases.append(a)
            seen.add(a)
        m["aliases"] = aliases
    return [by_id[i] for i in order]


def main() -> None:
    nova_prices = fetch_nova_prices()
    bedrock_models = fetch_bedrock_models()
    models = build(nova_prices, bedrock_models)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"models": models}
    OUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if INSTALLED.parent.exists() and OUT.resolve() != INSTALLED.resolve():
        shutil.copy2(OUT, INSTALLED)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1
        for m in models
        if (m.get("pricing") or {}).get("input_per_1m") is not None
        or (m.get("extra") or {}).get("price_per_image_std_le_1024") is not None
        or (m.get("extra") or {}).get("price_per_second_720p") is not None
        or (m.get("extra") or {}).get("text_input_per_1m") is not None
    )
    print(
        f"amazon.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    print(f"Nova pricing source mode: {NOVA_PRICING_MODE}", flush=True)
    for m in models:
        p = m.get("pricing") or {}
        pin = p.get("input_per_1m")
        pout = p.get("output_per_1m")
        if pin is not None:
            print(
                f"  {m['model_id']:36} ${pin}/${pout} ctx={m['context_window']}",
                flush=True,
            )
        else:
            unit = (m.get("extra") or {}).get("unit", "specialty")
            print(
                f"  {m['model_id']:36} specialty({unit}) ctx={m['context_window']}",
                flush=True,
            )


if __name__ == "__main__":
    main()
