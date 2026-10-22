"""Update the OpenAI catalog from the official model and pricing documentation.

This updater deliberately does not maintain a hard-coded model list.  The
official models index is the source of truth; existing records are retained
only when a model is not present in the current index (legacy compatibility).
"""

from __future__ import annotations

import json
import re
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from _image_capability_postprocess import (
    minimal_image_capability,
    parse_image_input_constraints,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "openai.json"
# The /models/all page is the official complete catalog.  We use its
# documented Markdown representation so the model links can be parsed without
# browser rendering, then fetch each linked model page for model-specific
# reasoning.effort values.
MODELS_URL = "https://developers.openai.com/api/docs/models/all.md"
PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
BASE = "https://developers.openai.com"
LIFE_SCIENCES_SOURCE = PRICING_URL.removesuffix(".md")
LIFE_SCIENCES_ACCESS_URL = "https://help.openai.com/en/articles/20001193-gpt-rosalind-for-life-sciences-research"
ENDPOINT = {
    "base_url": "https://api.openai.com/v1",
    "protocol": "openai-compatible",
    "auth": "bearer",
    "source": "https://platform.openai.com/docs/api-reference",
}


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "llmcapa-openai-updater/1.0"})
    with urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
        return r.read().decode("utf-8")


def number(text: str, default: int = 0) -> int:
    m = re.search(r"[\d,]+", text)
    return int(m.group(0).replace(",", "")) if m else default


def parse_reasoning_effort_values(text: str) -> list[str]:
    """Extract the documented reasoning.effort enum from a model page."""
    effort = re.search(r"Reasoning\.effort supports:?\s*([^.]+)", text, re.IGNORECASE)
    if not effort:
        return []
    values = re.split(r"\s*,\s*|\s+and\s+", effort.group(1).strip())
    cleaned = []
    for value in values:
        value = re.sub(r"\s*\(default\)", "", value, flags=re.IGNORECASE)
        value = re.sub(r"^and\s+", "", value.strip(), flags=re.IGNORECASE)
        value = value.strip().strip("`'\"").strip().rstrip(".").lower()
        if value:
            cleaned.append(value)
    return cleaned


def parse_supported_tools(text: str) -> set[str] | None:
    """Parse a model page's Responses API supported-tools list if present."""
    section = re.search(
        r"^##\s+Supported tools\s*$\n(.*?)(?=^##\s|\Z)",
        text,
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    if not section:
        return None
    return set(
        re.findall(
            r"^-\s+`?([a-z][a-z0-9_]*)`?\s*$",
            section.group(1),
            re.IGNORECASE | re.MULTILINE,
        )
    )


def parse_computer_use_capability(
    model_id: str, path: str, supported_tools: set[str] | None
) -> dict | None:
    """Build normalized Computer Use metadata when OpenAI documents the tool.

    The model pages' supported-tools list is authoritative for whether a model
    can use Computer Use through the Responses API. The list does not document
    the individual action schema or supported environments, so leave those
    optional fields unset rather than inferring them from the legacy preview.
    """
    if supported_tools is None or "computer_use" not in supported_tools:
        return None
    return {
        "supported": True,
        "native": True,
        "provider": "openai",
        "model": model_id,
        "api_type": "responses",
        "tool_type": "computer_use",
        "status": "documented",
        "source_url": BASE + path.removesuffix(".md"),
        "checked_at": datetime.now(timezone.utc).date().isoformat(),
    }


def parse_reasoning_mode_values(
    model_id: str, supports_responses_api: bool
) -> list[str]:
    """Return modes documented by OpenAI's GPT-5.6/GPT-6 reasoning guide."""
    if supports_responses_api and re.match(r"^gpt-(?:5\.6|6)(?:-|$)", model_id.lower()):
        return ["standard", "pro"]
    return []


def detail(path: str) -> dict:
    text = fetch(BASE + path)
    model = re.search(r"Model ID:\s*`([^`]+)`", text)
    if not model:
        return {}
    mid = model.group(1)

    def line(pattern: str, default: int = 0) -> int:
        m = re.search(pattern, text, re.IGNORECASE)
        return number(m.group(1), default) if m else default

    inp = re.search(r"Input modalities:\s*([^\n]+)", text, re.IGNORECASE)
    out = re.search(r"Output modalities:\s*([^\n]+)", text, re.IGNORECASE)
    input_modalities = (
        [x.strip().lower() for x in re.split(r"[,/]", inp.group(1))]
        if inp
        else ["text"]
    )
    output_modalities = (
        [x.strip().lower() for x in re.split(r"[,/]", out.group(1))]
        if out
        else ["text"]
    )
    features = set(re.findall(r"^- ([a-z_]+)\s*$", text, re.IGNORECASE | re.MULTILINE))

    def supported(name: str) -> bool:
        m = re.search(
            rf"\|\s*{re.escape(name)}[^|]*\|\s*[^|]*\|\s*(Supported|Not supported)",
            text,
            re.IGNORECASE,
        )
        return bool(m and m.group(1).lower() == "supported")

    aliases = (
        re.findall(r"^- `([^`]+)`$", text[text.find("## Snapshots") :], re.MULTILINE)
        if "## Snapshots" in text
        else []
    )
    aliases.extend(
        re.findall(r"`([^`]+)`\s+alias routes requests to", text, re.IGNORECASE)
    )
    aliases = list(dict.fromkeys(aliases))
    extra = {"source": BASE + path, "endpoints": [ENDPOINT]}
    default = re.search(r"Default snapshot:\s*`([^`]+)`", text, re.IGNORECASE)
    if default:
        extra["default_snapshot"] = default.group(1)
    if (
        "requires separate approval" in text.lower()
        or "required approval" in text.lower()
    ):
        extra["required_approval"] = True
    entry = {
        "provider": "openai",
        "model_id": mid,
        "display_name": (
            re.search(r"^#\s+(.+)$", text, re.MULTILINE).group(1).strip()
            if re.search(r"^#\s+(.+)$", text, re.MULTILINE)
            else mid
        ),
        "context_window": line(r"([\d,]+) context window"),
        "max_output_tokens": line(r"([\d,]+) max output tokens"),
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "deprecated": "deprecated" in text[:1000].lower(),
        "aliases": aliases,
        "extra": extra,
    }
    entry["supports_vision"] = "image" in input_modalities
    entry["supports_function_calling"] = "function_calling" in features
    entry["supports_json_mode"] = "structured_outputs" in features
    entry["supports_streaming"] = "streaming" in features
    entry["supports_responses_api"] = supported("Responses")
    entry["supports_chat_completion"] = supported("Chat Completions")
    supported_tools = parse_supported_tools(text)
    if supported_tools is not None:
        entry["supports_tool_search"] = bool(
            entry["supports_responses_api"] and "tool_search" in supported_tools
        )
    computer_use = parse_computer_use_capability(mid, path, supported_tools)
    if computer_use is not None:
        entry["computer_use"] = computer_use
    entry["supports_reasoning"] = (
        "reasoning token support" in text.lower() or "reasoning" in features
    )
    mode_values = parse_reasoning_mode_values(mid, entry["supports_responses_api"])
    if mode_values:
        entry["supports_reasoning_mode"] = True
        entry["reasoning_mode_values"] = mode_values
    effort_values = parse_reasoning_effort_values(text)
    if effort_values:
        entry["reasoning_effort_values"] = effort_values
    # OpenAI's o-series pages do not consistently repeat the enum, but the
    # official o-series documentation/API uses the same three levels.
    if (
        entry["supports_reasoning"]
        and "reasoning_effort_values" not in entry
        and re.match(r"^o(?:1|3|4)(?:-|$)", mid)
    ):
        entry["reasoning_effort_values"] = ["low", "medium", "high"]
    # Keep the boolean capability flag in sync with the discovered values.
    # Previously values were written without setting this flag, causing
    # reasoning-capable OpenAI models (for example gpt-6-astra) to report
    # supports("reasoning_effort") == False.
    entry["supports_reasoning_effort"] = bool(entry.get("reasoning_effort_values"))
    image = minimal_image_capability(entry)
    image_constraints = parse_image_input_constraints(text)
    if image is not None or image_constraints:
        image = image or {}
        image.update(image_constraints)
        image["source_url"] = BASE + path
        image["status"] = "documented"
        entry["image"] = image
    cutoff = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4}) knowledge cutoff", text)
    if cutoff:
        entry["knowledge_cutoff"] = cutoff.group(1)
    return entry


def parse_pricing_table(markdown: str) -> dict[str, dict[str, float]]:
    """Read named price columns rather than guessing their position.

    The official table can list Input, Cached input, and Output in different
    orders. Missing/unparseable rates must never be guessed.
    """
    result: dict[str, dict[str, float]] = {}
    header: dict[str, int] = {}

    for line in markdown.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            if stripped:
                header = {}
            continue
        columns = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(columns) < 3:
            continue

        if columns[0].strip("` ").casefold() in ("model", "model id"):
            normalized = [
                re.sub(r"[^a-z ]", " ", value.lower()).strip() for value in columns
            ]
            header = {}
            for index, value in enumerate(normalized):
                if "cached" in value and "input" in value:
                    header["cached_input_per_1m"] = index
                elif "input" in value:
                    header["input_per_1m"] = index
                elif "output" in value:
                    header["output_per_1m"] = index
            header["columns"] = len(columns)
            continue
        if not all(key in header for key in ("input_per_1m", "output_per_1m")):
            continue
        if len(columns) != header["columns"]:
            continue

        def rate_at(index: int) -> float | None:
            value = columns[index].strip().replace(",", "")
            match = re.match(r"^\$?\s*(\d+(?:\.\d+)?)", value)
            return float(match.group(1)) if match else None

        input_rate = rate_at(header["input_per_1m"])
        output_rate = rate_at(header["output_per_1m"])
        if input_rate is None or output_rate is None:
            continue

        name = columns[0].strip("` ")
        rates = {"input_per_1m": input_rate, "output_per_1m": output_rate}
        if "cached_input_per_1m" in header:
            cached_rate = rate_at(header["cached_input_per_1m"])
            if cached_rate is not None:
                rates["cached_input_per_1m"] = cached_rate
        result[name] = rates
    return result


def prices(markdown: str) -> dict[str, tuple[float, float]]:
    return {
        name: (rates["input_per_1m"], rates["output_per_1m"])
        for name, rates in parse_pricing_table(markdown).items()
    }


def parse_life_sciences_models(markdown: str) -> list[dict]:
    """Parse Rosalind models from the dedicated official pricing section.

    Rosalind model pages do not exist in the all-models index; use the
    separately labeled columns in the current life-sciences pricing table.
    """
    section_match = re.search(
        r"(?ims)^Life sciences models[ \t]*\r?\n(.*?)(?=^Multimodal models[ \t]*$|\Z)",
        markdown,
    )
    if not section_match:
        return []

    section = section_match.group(1)
    approval_required = bool(
        re.search(r"Access is limited to approved", section, re.IGNORECASE)
    )
    access_link = re.search(
        r"\[trusted-access program\]\((https?://[^)]+)\)",
        section,
        re.IGNORECASE,
    )
    models = []
    for model_id, rates in parse_pricing_table(section).items():
        if not re.fullmatch(r"gpt-rosalind-[a-z0-9-]+", model_id, re.IGNORECASE):
            continue
        if "cached_input_per_1m" not in rates:
            continue
        models.append(
            {
                "model_id": model_id,
                **rates,
                "required_approval": approval_required,
                "access_program_url": (
                    access_link.group(1)
                    if access_link
                    else LIFE_SCIENCES_ACCESS_URL if approval_required else None
                ),
            }
        )
    return models


def life_sciences_catalog_entry(model: dict, previous: dict | None = None) -> dict:
    """Create/update a pricing-only Rosalind record without guessing capabilities."""
    entry = dict(previous or {})
    entry.update(
        {
            "provider": "openai",
            "model_id": model["model_id"],
            "display_name": "GPT-Rosalind "
            + model["model_id"].removeprefix("gpt-rosalind-").replace("-", " ").title(),
            "context_window": entry.get("context_window", 0),
            "max_output_tokens": entry.get("max_output_tokens", 0),
            "input_modalities": entry.get("input_modalities", ["text"]),
            "output_modalities": entry.get("output_modalities", ["text"]),
            "deprecated": entry.get("deprecated", False),
            "aliases": entry.get("aliases", []),
            "pricing": {
                "input_per_1m": model["input_per_1m"],
                "output_per_1m": model["output_per_1m"],
                "currency": "USD",
            },
        }
    )
    # Pricing is documented, but a separate model page does not document these
    # API features. Keep them unknown instead of inheriting dataclass defaults.
    for field in (
        "supports_chat_completion",
        "supports_responses_api",
        "supports_streaming",
        "supports_function_calling",
        "supports_json_mode",
        "supports_vision",
        "supports_reasoning",
        "supports_reasoning_effort",
        "supports_thinking_budget",
        "supports_thinking_level",
        "supports_fim",
        "supports_anthropic_api",
        "supports_google_api",
        "supports_realtime",
    ):
        entry.setdefault(field, None)
    extra = dict(entry.get("extra") or {})
    extra.update(
        {
            "source": LIFE_SCIENCES_SOURCE,
            "spec_status": "pricing_only",
            "required_approval": model["required_approval"],
            "cached_input_per_1m": model["cached_input_per_1m"],
        }
    )
    if model["access_program_url"]:
        extra["access_program_url"] = model["access_program_url"]
    entry["extra"] = extra
    return entry


def parse_model_index(index: str) -> tuple[list[str], set[str]]:
    """Return model-page paths and those explicitly marked Deprecated."""
    rows = re.findall(
        r"^- \[[^\]]+\]\((/api/docs/models/[^)]+\.md)\)(?::\s*([^\n]*))?",
        index,
        re.MULTILINE,
    )
    paths = [path for path, _ in rows]
    deprecated = {
        path
        for path, description in rows
        if re.match(r"\s*Deprecated\b", description or "", re.IGNORECASE)
    }
    return paths, deprecated


def preserve_curated_decision(old: dict, refreshed: dict) -> dict:
    """Keep endpoint-specific Decisions metadata across model-page refreshes."""
    if old.get("decision") is None:
        return refreshed
    if refreshed.get("decision") is None:
        refreshed["decision"] = old["decision"]
    if "decision" in old.get("output_modalities", []):
        modalities = refreshed.setdefault("output_modalities", [])
        if "decision" not in modalities:
            modalities.append("decision")
    return refreshed


def main() -> None:
    index = fetch(MODELS_URL)
    pricing_markdown = fetch(PRICING_URL)
    pricing = prices(pricing_markdown.split("### Batch pricing data", 1)[0])
    life_sciences_models = parse_life_sciences_models(pricing_markdown)
    links, deprecated_paths = parse_model_index(index)
    current = json.loads(DATA.read_text(encoding="utf-8"))
    current_by_id = {m.get("model_id"): m for m in current.get("models", [])}
    updated, seen = [], set()
    for path in dict.fromkeys(links):
        try:
            entry = detail(path)
        except Exception as exc:  # noqa: BLE001
            print(f"skip {path}: {exc}")
            continue
        if not entry:
            continue
        mid = entry["model_id"]
        if path in deprecated_paths:
            entry["deprecated"] = True
        # Preserve library-specific metadata unless the official page replaces it.
        if mid in current_by_id:
            old = current_by_id[mid]
            merged = dict(old)
            merged.update(entry)
            merged["extra"] = {**old.get("extra", {}), **entry.get("extra", {})}
            # The model detail page is authoritative for fields it exposes,
            # but it does not always repeat the full image capability matrix.
            # Keep previously documented nested image constraints instead of
            # replacing them with the parser's minimal capability record.
            if old.get("image") and entry.get("image"):
                merged["image"] = {**old["image"], **entry["image"]}
                if old["image"].get("endpoints") and entry["image"].get("endpoints"):
                    merged["image"]["endpoints"] = {
                        **old["image"]["endpoints"],
                        **entry["image"]["endpoints"],
                    }
            # Some official model pages omit the Reasoning.effort enum even
            # when the existing catalog has verified values. Do not replace
            # that metadata with the parser's default False; retain it unless
            # the page supplies a new non-empty enum.
            if not entry.get("reasoning_effort_values") and old.get(
                "reasoning_effort_values"
            ):
                merged["reasoning_effort_values"] = old["reasoning_effort_values"]
                merged["supports_reasoning_effort"] = True
            if (
                entry.get("supports_tool_search") is None
                and old.get("supports_tool_search") is not None
            ):
                merged["supports_tool_search"] = old["supports_tool_search"]
            if not entry.get("reasoning_mode_values") and old.get(
                "reasoning_mode_values"
            ):
                merged["reasoning_mode_values"] = old["reasoning_mode_values"]
                merged["supports_reasoning_mode"] = old.get(
                    "supports_reasoning_mode", True
                )
            merged = preserve_curated_decision(old, merged)
            entry = merged
        price_id = entry.get("extra", {}).get("default_snapshot", mid)
        rate = pricing.get(price_id) or pricing.get(mid)
        if rate:
            i, o = rate
            entry["pricing"] = {
                "input_per_1m": i,
                "output_per_1m": o,
                "currency": "USD",
            }
        else:
            # The pricing page may omit older models. Keep documented
            # historical rates instead of turning valid prices into null.
            entry.setdefault(
                "pricing",
                {"input_per_1m": None, "output_per_1m": None, "currency": "USD"},
            )
        updated.append(entry)
        seen.add(mid)
    pages_discovered = len(seen)
    updated_by_id = {entry.get("model_id"): i for i, entry in enumerate(updated)}
    for model in life_sciences_models:
        mid = model["model_id"]
        index_in_updated = updated_by_id.get(mid)
        previous = (
            updated[index_in_updated]
            if index_in_updated is not None
            else current_by_id.get(mid)
        )
        entry = life_sciences_catalog_entry(model, previous)
        if index_in_updated is None:
            updated_by_id[mid] = len(updated)
            updated.append(entry)
        else:
            updated[index_in_updated] = entry
        seen.add(mid)
    for old in current.get("models", []):
        if old.get("model_id") not in seen:
            updated.append(old)
    updated.sort(key=lambda x: x.get("model_id", ""))
    payload = json.dumps({"models": updated}, ensure_ascii=False, indent=2) + "\n"
    DATA.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))
    with (ROOT / "provider_update_log.md").open("a", encoding="utf-8", newline="") as f:
        f.write(
            f"\r\n## OpenAI ({datetime.now(timezone.utc).date():%Y-%m-%d})\r\n\r\n- Source: {MODELS_URL}\r\n- Source: {PRICING_URL}\r\n- Dynamically discovered {pages_discovered} official model pages; life-sciences models added from pricing: {len(life_sciences_models)}; legacy records preserved: {len(updated)-len(seen)}\r\n"
        )
    print(
        f"openai.json: {len(updated)} models; discovered {pages_discovered} official "
        f"model pages and {len(life_sciences_models)} life-sciences pricing entries"
    )


if __name__ == "__main__":
    main()
