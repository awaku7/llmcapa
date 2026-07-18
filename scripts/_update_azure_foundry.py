"""Build/refresh azure_foundry.json from Foundry catalog + multi-provider pricing.

Sources:
- Catalog (chat-completion filter, Playwright paginate):
  https://ai.azure.com/catalog/models
  API: https://ai.azure.com/api/japaneast/asset-gallery/v1.0/models
  Scratch: _scratch_azure_catalog_raw.json (694 items)
- Pricing pages (Playwright tables):
  https://azure.microsoft.com/en-us/pricing/details/azure-openai/
  https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/{microsoft,mistral-ai,llama,cohere,deepseek,grok,kimi,fireworks,black-forest-labs}/
  Scratch: _scratch_azure_pricing_tables.json
  Manual AOAI extract: _scratch_azure_aoai_pricing_tables.json

Notes:
- microsoft.json already holds Microsoft-owned PAYG (Phi/MAI) in depth;
  azure_foundry is the broader multi-vendor Foundry catalog and must NOT be
  collapsed into microsoft.json.
- Prefer Global Standard PAYG rates as top-level pricing; Data Zone / Regional /
  Priority / Batch / cache live under extra.
- Hugging Face VM-only research models without MaaS/paygo are kept only when
  they appear in the chat-completion catalog scrape (task filter already applied).
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

WORKDIR = Path(r"F:\KAIHATSU\llmcapa")
OUT = WORKDIR / "src" / "llmcapa" / "data" / "azure_foundry.json"
INSTALLED = Path(r"F:\Python314\Lib\site-packages\llmcapa\data\azure_foundry.json")
LOG = WORKDIR / "provider_update_log.md"
CATALOG = WORKDIR / "_scratch_azure_catalog_raw.json"
PRICING = WORKDIR / "_scratch_azure_pricing_tables.json"
AOAI_PRICING = WORKDIR / "_scratch_azure_aoai_pricing_tables.json"

SOURCE_CATALOG = "https://ai.azure.com/catalog/models"
SOURCE_AOAI = "https://azure.microsoft.com/en-us/pricing/details/azure-openai/"
SOURCE_FOUNDRY_MODELS = (
    "https://azure.microsoft.com/en-us/pricing/details/ai-foundry-models/"
)

PUBLISHER_TO_PROVIDER = {
    "openai": "azure-openai",
    "microsoft": "microsoft",
    "meta": "meta",
    "mistral ai": "mistral",
    "mistral": "mistral",
    "cohere": "cohere",
    "deepseek": "deepseek",
    "xai": "xai",
    "moonshot ai": "moonshot",
    "moonshot": "moonshot",
    "fireworks": "fireworks",
    "nvidia": "nvidia",
    "hugging face": "huggingface",
    "alibaba": "alibaba",
    "anthropic": "anthropic",
    "black forest labs": "black-forest-labs",
    "ntt data": "ntt-data",
    "databricks": "databricks",
    "snowflake": "snowflake",
    "gretel": "gretel",
    "inception": "inception",
    "domyn": "domyn",
    "rezolveai": "rezolveai",
    "bosonai": "bosonai",
    "cerence": "cerence",
    "bayer": "bayer",
    "sdaia": "sdaia",
    "azureml-foundrylocalonazurelocal": "foundry-local",
}

# Known context / max_out overrides when catalog lacks limits
KNOWN_LIMITS: dict[str, tuple[int, int]] = {
    # OpenAI AOAI (common)
    "gpt-5.5": (1_050_000, 128_000),
    "gpt-5.4": (1_050_000, 128_000),
    "gpt-5.4-pro": (1_050_000, 128_000),
    "gpt-5.4-mini": (400_000, 128_000),
    "gpt-5.4-nano": (400_000, 128_000),
    "gpt-5.3-codex": (400_000, 128_000),
    "gpt-5.3-chat": (128_000, 16_384),
    "gpt-5.2": (400_000, 128_000),
    "gpt-5.2-chat": (128_000, 16_384),
    "gpt-5.1": (400_000, 128_000),
    "gpt-5.1-chat": (128_000, 16_384),
    "gpt-5.1-codex": (400_000, 128_000),
    "gpt-5.1-codex-max": (400_000, 128_000),
    "gpt-5.1-codex-mini": (400_000, 128_000),
    "gpt-5": (400_000, 128_000),
    "gpt-5-chat": (128_000, 16_384),
    "gpt-5-pro": (400_000, 272_000),
    "gpt-5-codex": (400_000, 128_000),
    "gpt-5-mini": (400_000, 128_000),
    "gpt-5-nano": (400_000, 128_000),
    "gpt-4.1": (1_047_576, 32_768),
    "gpt-4.1-mini": (1_047_576, 32_768),
    "gpt-4.1-nano": (1_047_576, 32_768),
    "gpt-4o": (128_000, 16_384),
    "gpt-4o-mini": (128_000, 16_384),
    "o1": (200_000, 100_000),
    "o1-mini": (128_000, 65_536),
    "o3": (200_000, 100_000),
    "o3-mini": (200_000, 100_000),
    "o4-mini": (200_000, 100_000),
    "o3-deep-research": (200_000, 100_000),
    "text-embedding-3-large": (8191, 0),
    "text-embedding-3-small": (8191, 0),
    "text-embedding-ada-002": (8191, 0),
    # Partner MaaS (from prior catalog / public cards)
    "deepseek-v3.2": (128_000, 8_192),
    "deepseek-r1": (128_000, 8_192),
    "deepseek-v3": (128_000, 8_192),
    "deepseek-v3-0324": (128_000, 8_192),
    "grok-3": (131_072, 16_384),
    "grok-3-mini": (131_072, 16_384),
    "grok-code-fast-1": (256_000, 16_384),
    "kimi-k2-thinking": (262_144, 16_384),
    "kimi-k2.5": (262_144, 16_384),
    "kimi-k2.6": (262_144, 16_384),
    "llama-3.3-70b-instruct": (128_000, 8_192),
    "llama-4-maverick-17b-128e-instruct-fp8": (1_000_000, 16_384),
    "mai-ds-r1": (128_000, 8_192),
    "phi-4": (16_384, 16_384),
    "phi-4-mini": (128_000, 8_192),
    "phi-4-multimodal-instruct": (128_000, 8_192),
    "phi-4-reasoning": (32_768, 16_384),
    "phi-4-reasoning-plus": (32_768, 16_384),
    "cohere-command-a": (256_000, 8_192),
    "cohere-command-r-plus-08-2024": (128_000, 4_096),
    "cohere-command-r-08-2024": (128_000, 4_096),
}


def _money(s: str) -> float | None:
    if s is None:
        return None
    t = str(s).strip()
    if not t or t.upper() in {"N/A", "NA", "-", "—", "–"}:
        return None
    # strip currency words
    t = t.replace(",", "")
    m = re.search(r"\$?\s*([0-9]+(?:\.[0-9]+)?)", t)
    if not m:
        return None
    return float(m.group(1))


def _parse_inline_pricing(text: str) -> dict[str, float]:
    """Parse 'Input: $x Cached Input: $y Output: $z' style blobs."""
    out: dict[str, float] = {}
    if not text or text.upper() == "N/A":
        return out
    patterns = [
        (r"Cached\s*Input(?:\s*Text)?\s*:\s*\$?\s*([0-9.]+)", "cached_input_per_1m"),
        (r"Input(?:\s*Text)?\s*:\s*\$?\s*([0-9.]+)", "input_per_1m"),
        (r"Output(?:\s*Text)?\s*:\s*\$?\s*([0-9.]+)", "output_per_1m"),
        (r"Input\s*Image\s*:\s*\$?\s*([0-9.]+)", "input_image_per_1m"),
        (r"Cached\s*Input\s*Image\s*:\s*\$?\s*([0-9.]+)", "cached_input_image_per_1m"),
        (r"Output\s*Image\s*:\s*\$?\s*([0-9.]+)", "output_image_per_1m"),
        (r"Audio\s*Input\s*:\s*\$?\s*([0-9.]+)", "audio_input_per_1m"),
        (r"Audio\s*Output\s*:\s*\$?\s*([0-9.]+)", "audio_output_per_1m"),
        (r"Text\s*Input\s*:\s*\$?\s*([0-9.]+)", "input_per_1m"),
        (r"Text\s*Output\s*:\s*\$?\s*([0-9.]+)", "output_per_1m"),
    ]
    # Prefer more specific patterns first — already ordered
    used_spans: list[tuple[int, int]] = []
    for pat, key in patterns:
        for m in re.finditer(pat, text, flags=re.I):
            span = m.span()
            # skip if overlaps a more-specific earlier match for cached*
            if any(not (span[1] <= a or span[0] >= b) for a, b in used_spans):
                continue
            # For Input: avoid matching inside Cached Input
            if key == "input_per_1m":
                start = m.start()
                prefix = text[max(0, start - 10) : start].lower()
                if "cached" in prefix:
                    continue
            out[key] = float(m.group(1))
            used_spans.append(span)
            break
    # /1K Tokens style (Cohere)
    m = re.search(
        r"Input:\s*\$?([0-9.]+)\s*/\s*1K\s*Tokens.*?Output:\s*\$?([0-9.]+)\s*/\s*1K",
        text,
        flags=re.I | re.S,
    )
    if m:
        out["input_per_1m"] = float(m.group(1)) * 1000
        out["output_per_1m"] = float(m.group(2)) * 1000
    # Fireworks style with /1M Tokens already
    m = re.search(
        r"Input:\s*\$?([0-9.]+)/1M\s*Tokens.*?Cached\s*Input:\s*\$?([0-9.]+)/1M\s*Tokens.*?Output:\s*\$?([0-9.]+)/1M",
        text,
        flags=re.I | re.S,
    )
    if m:
        out["input_per_1m"] = float(m.group(1))
        out["cached_input_per_1m"] = float(m.group(2))
        out["output_per_1m"] = float(m.group(3))
    return out


def _norm_key(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s)
    # drop zone suffixes for matching
    s = re.sub(
        r"\s*(\(|$)\s*(global|data\s*zone|datazone|regional|us/eu\s*[-–]?\s*data\s*zones?|long\s*context).*$",
        "",
        s,
        flags=re.I,
    )
    s = re.sub(r"[^a-z0-9.+]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    # common aliases
    repl = {
        "gpt-chat-latest-05052026": "gpt-chat-latest",
        "gpt-5-2025-08-07": "gpt-5",
        "gpt-5-2-chat-latest": "gpt-5.2-chat",
        "gpt-5-2-chat": "gpt-5.2-chat",
        "gpt-5-2-codex": "gpt-5.2-codex",
        "gpt-5-2": "gpt-5.2",
        "gpt-5-1-chat": "gpt-5.1-chat",
        "gpt-5-1-codex-max": "gpt-5.1-codex-max",
        "gpt-5-1-codex-mini": "gpt-5.1-codex-mini",
        "gpt-5-1-codex": "gpt-5.1-codex",
        "gpt-5-1": "gpt-5.1",
        "gpt-5-3-codex": "gpt-5.3-codex",
        "gpt-5-3-chat": "gpt-5.3-chat",
        "gpt-5-4-pro": "gpt-5.4-pro",
        "gpt-5-4-mini": "gpt-5.4-mini",
        "gpt-5-4-nano": "gpt-5.4-nano",
        "gpt-5-4": "gpt-5.4",
        "gpt-5-5": "gpt-5.5",
        "gpt-4-1-2025-04-14": "gpt-4.1",
        "gpt-4-1-mini-2025-04-14": "gpt-4.1-mini",
        "gpt-4-1-nano-2025-04-14": "gpt-4.1-nano",
        "gpt-4-1-mini": "gpt-4.1-mini",
        "gpt-4-1-nano": "gpt-4.1-nano",
        "gpt-4-1": "gpt-4.1",
        "gpt-4o-2024-1120": "gpt-4o",
        "gpt-4o-2024-08-06": "gpt-4o-2024-08-06",
        "gpt-4o-2024-0513": "gpt-4o-2024-05-13",
        "gpt-4o-mini-0718": "gpt-4o-mini",
        "o3-2025-04-16": "o3",
        "o4-mini-2025-04-16": "o4-mini",
        "o3-mini-2025-01-31": "o3-mini",
        "o1-2024-12-17": "o1",
        "o1-mini-2024-09-12": "o1-mini",
        "o3-deep-research": "o3-deep-research",
        "deepseek-v3-2": "deepseek-v3.2",
        "deepseek-v3-2-sp": "deepseek-v3.2-sp",
        "deepseek-v3-0324": "deepseek-v3-0324",
        "llama-3-3-70b": "llama-3.3-70b-instruct",
        "llama-3.3-70b": "llama-3.3-70b-instruct",
        "llama4-maverick-17b": "llama-4-maverick-17b-128e-instruct-fp8",
        "llama4-mavrick-17b": "llama-4-maverick-17b-128e-instruct-fp8",
        "llama-4-maverick-17b": "llama-4-maverick-17b-128e-instruct-fp8",
        # xAI catalog ids use 4-1 / 4-20; pricing pages use 4.1 / 4.2
        "grok-4-1-fast": "grok-4.1-fast",
        "grok-4-1-fast-reasoning": "grok-4.1-fast",
        "grok-4-1-fast-non-reasoning": "grok-4.1-fast",
        "grok-4-20": "grok-4.2",
        "grok-4-20-reasoning": "grok-4.2",
        "grok-4-20-non-reasoning": "grok-4.2",
        "phi-4-multimodal-instruct": "phi-4-multimodal-text-and-image",
        "phi-4-multimodal": "phi-4-multimodal-text-and-image",
        "phi-4-multimodal-instruct": "phi-4-multimodal-text-and-image",
        "deepseek-v3.2-speciale": "deepseek-v3.2-sp",
        "deepseek-v3-2-speciale": "deepseek-v3.2-sp",
        "deepseek-r1-0528": "deepseek-r1",
        "mai-image-2e": "mai-image-2-efficient",
        "mai-image-2-e": "mai-image-2-efficient",
        "cohere-command-a-plus": "cohere-command-a",
        "cohere-command-a-plus-05-2026": "cohere-command-a",
        "command-a-plus": "cohere-command-a",
        "command-a": "cohere-command-a",
        "kimi-k2-thinking": "kimi-k2-thinking",
        "kimi-k2-5-thinking": "kimi-k2.5",
        "kimi-k2.5-thinking": "kimi-k2.5",
        "kimi-k2-6-thinking": "kimi-k2.6",
        "kimi-k2.6-thinking": "kimi-k2.6",
        "grok-code-fast-1": "grok-code-fast-1",
        "mai-ds-r1": "mai-ds-r1",
        "mai-image-2": "mai-image-2",
        "mai-image-2-efficient": "mai-image-2-efficient",
        "cohere-command-a": "cohere-command-a",
        "fw-deepseek-v4-pro": "fw-deepseek-v4-pro",
        "fw-glm-5-1": "fw-glm-5.1",
        "fw-kimi-k2-6": "fw-kimi-k2.6",
        "fw-minimax-2-7": "fw-minimax-2.7",
        "phi-3-mini-4k-instruct": "phi-3-mini-4k-instruct",
        "phi-3-mini-128k-instruct": "phi-3-mini-128k-instruct",
        "phi-3.5-mini-instruct": "phi-3.5-mini-instruct",
        "phi-3-small-8k-instruct": "phi-3-small-8k-instruct",
        "phi-3-small-128k-instruct": "phi-3-small-128k-instruct",
        "phi-3-medium-4k-instruct": "phi-3-medium-4k-instruct",
        "phi-3-medium-128k-instruct": "phi-3-medium-128k-instruct",
        "phi-3.5-moe-instruct": "phi-3.5-moe-instruct",
        "phi-4": "phi-4",
        "phi-4-mini-instruct": "phi-4-mini-instruct",
        "phi-4-mini-reasoning": "phi-4-mini-reasoning",
        "phi-4-reasoning": "phi-4-reasoning",
        "phi-4-reasoning-plus": "phi-4-reasoning-plus",
        "gpt-oss-120b": "gpt-oss-120b",
        "ada": "text-embedding-ada-002",
        "text-embedding-3-large": "text-embedding-3-large",
        "text-embedding-3-small": "text-embedding-3-small",
    }
    # strip context-length parenthetical already handled
    s2 = re.sub(r"-?\d+k-context-length", "", s)
    s2 = re.sub(r"-+", "-", s2).strip("-")
    if s2 in repl:
        return repl[s2]
    if s in repl:
        return repl[s]
    # try without trailing version dates
    s3 = re.sub(r"-\d{4}-\d{2}-\d{2}$", "", s2)
    if s3 in repl:
        return repl[s3]
    return s2 or s


def _zone_of(label: str) -> str:
    t = label.lower()
    if "long context" in t:
        return "long_context"
    if "data zone" in t or "datazone" in t or "us/eu" in t:
        return "data_zone"
    if "regional" in t:
        return "regional"
    if "global" in t:
        return "global"
    return "global"


def _detect_zone_and_base(model_label: str) -> tuple[str, str]:
    zone = _zone_of(model_label)
    # strip zone words and parentheticals for base key
    base = model_label
    base = re.sub(r"\([^)]*context[^)]*\)", "", base, flags=re.I)
    base = re.sub(
        r"\b(Global|Data\s*Zone|DataZone|Regional|US/EU\s*[-–]?\s*Data\s*Zones?|Long\s*Context)\b",
        "",
        base,
        flags=re.I,
    )
    base = re.sub(r"\s+", " ", base).strip(" -")
    return zone, _norm_key(base)


def parse_aoai_tables(tables: list[dict]) -> dict[str, dict]:
    """Return model_key -> {global: pricing, data_zone:..., priority:..., batch:..., long_context:...}."""
    store: dict[str, dict] = {}

    def ensure(k: str) -> dict:
        return store.setdefault(k, {})

    for tb in tables:
        rows = tb.get("rows") or []
        if len(rows) < 2:
            continue
        header = [c.lower() for c in rows[0]]
        # skip GPU / PTU-only / non-token tables lightly
        joined_h = " | ".join(header)
        if "gpu" in joined_h and "compute" in joined_h:
            continue
        if "min ptu" in joined_h:
            continue

        # Embedding per 1K
        if "per 1,000 tokens" in joined_h or "per 1.000 tokens" in joined_h:
            for r in rows[1:]:
                if not r:
                    continue
                label = r[0]
                zone, key = _detect_zone_and_base(label)
                if not key:
                    continue
                price = _money(r[1]) if len(r) > 1 else None
                if price is None:
                    continue
                # convert per 1K -> per 1M
                slot = ensure(key).setdefault(zone, {})
                slot["input_per_1m"] = price * 1000
                slot["output_per_1m"] = 0.0
                slot["unit"] = "tokens"
            continue

        # Legacy language models with separate input/output columns
        if "input (per 1m" in joined_h and "output (per 1m" in joined_h:
            # find col indices
            try:
                ci = next(i for i, h in enumerate(header) if h.startswith("input"))
                co = next(i for i, h in enumerate(header) if h.startswith("output"))
            except StopIteration:
                ci, co = 2, 3
            for r in rows[1:]:
                if len(r) <= max(ci, co):
                    continue
                label = r[0]
                zone, key = _detect_zone_and_base(label)
                if not key:
                    continue
                inp, outp = _money(r[ci]), _money(r[co])
                if inp is None and outp is None:
                    continue
                slot = ensure(key).setdefault(zone, {})
                if inp is not None:
                    slot["input_per_1m"] = inp
                if outp is not None:
                    slot["output_per_1m"] = outp
            continue

        # Standard AOAI multi-col: Model | Pricing | Priority | Batch
        # Fine-tune tables put model name only on first row; later rows are bare
        # zone labels ("Global", "Data Zone", "Developer") — carry model forward.
        prev_model_label = ""
        for r in rows[1:]:
            if not r:
                continue
            label = (r[0] or "").strip()
            zone_only = _norm_key(label) in (
                "",
                "global",
                "regional",
                "data-zone",
                "datazone",
                "developer",
                "long-context",
            )
            if zone_only and prev_model_label:
                label = f"{prev_model_label} {label}"
            elif not zone_only:
                prev_model_label = re.sub(
                    r"\b(Global|Data\s*Zone|DataZone|Regional|Developer|Long\s*Context)\b.*$",
                    "",
                    label,
                    flags=re.I,
                ).strip(" -") or label
            zone, key = _detect_zone_and_base(label)
            if not key:
                continue
            # long context flag from label
            if "long context" in label.lower():
                zone = "long_context"
            # context threshold note
            ctx_note = None
            mctx = re.search(r"\(([<>]=?\s*\d+\s*k[^\)]*)\)", label, flags=re.I)
            if mctx:
                ctx_note = mctx.group(1).strip()
                # ">272k" = long-context tier; "<272k" = standard tier for that zone
                if ctx_note.lstrip().startswith(">"):
                    zone = "long_context" if zone == "global" else f"{zone}_long_context"

            for col_i, col_name in enumerate(r[1:], start=1):
                blob = r[col_i] if col_i < len(r) else ""
                if not blob or blob.upper() == "N/A":
                    continue
                parsed = _parse_inline_pricing(blob)
                if not parsed and _money(blob) is not None and col_i == 1:
                    # single number unlikely
                    continue
                if not parsed:
                    continue
                # which tier?
                h = header[col_i] if col_i < len(header) else ""
                if "priority" in h:
                    tier = "priority"
                elif "batch" in h:
                    tier = "batch"
                else:
                    tier = zone  # global/data_zone/regional/long_context
                slot = ensure(key).setdefault(tier, {})
                # Prefer standard (<Nk) rates; do not let long-context overwrite
                if slot and "input_per_1m" in slot and ctx_note and ctx_note.lstrip().startswith(">"):
                    # should have been routed to long_context; skip overwrite
                    if tier not in ("long_context",) and not str(tier).endswith("_long_context"):
                        # force long_context bucket
                        tier = "long_context" if tier == "global" else f"{tier}_long_context"
                        slot = ensure(key).setdefault(tier, {})
                if not slot or "input_per_1m" not in slot:
                    slot.update(parsed)
                elif ctx_note and ctx_note.lstrip().startswith("<"):
                    # standard rate wins over any prior long-context mis-bucket
                    slot.update(parsed)
                if ctx_note:
                    slot["context_note"] = ctx_note
    return store


def parse_simple_token_tables(tables: list[dict]) -> dict[str, dict]:
    """Foundry partner pages: Models | Input | Output columns."""
    store: dict[str, dict] = {}
    for tb in tables:
        rows = tb.get("rows") or []
        if len(rows) < 2:
            continue
        header = [c.lower() for c in rows[0]]
        joined = " | ".join(header)
        if "gpu" in joined:
            continue
        if "min ptu" in joined:
            continue
        # Input/Output columns
        if "input" in joined and "output" in joined and "per 1m" in joined:
            try:
                ci = next(i for i, h in enumerate(header) if "input" in h)
                co = next(i for i, h in enumerate(header) if "output" in h)
            except StopIteration:
                continue
            for r in rows[1:]:
                if len(r) <= max(ci, co):
                    continue
                zone, key = _detect_zone_and_base(r[0])
                if not key:
                    continue
                inp, outp = _money(r[ci]), _money(r[co])
                if inp is None and outp is None:
                    continue
                slot = store.setdefault(key, {}).setdefault(zone, {})
                if inp is not None:
                    slot["input_per_1m"] = inp
                if outp is not None:
                    slot["output_per_1m"] = outp
            continue
        # single Price column with inline Input/Output
        if header[-1].startswith("price") or header[-1] == "price":
            for r in rows[1:]:
                if len(r) < 2:
                    continue
                zone, key = _detect_zone_and_base(r[0])
                if not key:
                    continue
                blob = r[-1]
                # skip non-token (rerank / image / pages)
                if "/1k searches" in blob.lower() or "/image" in blob.lower() or "pages" in blob.lower():
                    # still record special
                    if "searches" in blob.lower():
                        m = _money(blob)
                        if m is not None:
                            store.setdefault(key, {}).setdefault(zone, {}).update(
                                {
                                    "unit": "1k_searches",
                                    "price_per_1k_searches": m,
                                }
                            )
                    elif "megapixel" in blob.lower() or "/image" in blob.lower() or "images" in blob.lower():
                        m = _money(blob)
                        if m is not None:
                            store.setdefault(key, {}).setdefault(zone, {}).update(
                                {
                                    "unit": "image",
                                    "price_per_unit": m,
                                    "price_note": blob,
                                }
                            )
                    continue
                parsed = _parse_inline_pricing(blob)
                if parsed:
                    store.setdefault(key, {}).setdefault(zone, {}).update(parsed)
                else:
                    # Cohere embed style Text: $x/1K
                    m = re.search(r"Text:\s*\$?([0-9.]+)/1K", blob, flags=re.I)
                    if m:
                        store.setdefault(key, {}).setdefault(zone, {}).update(
                            {
                                "input_per_1m": float(m.group(1)) * 1000,
                                "output_per_1m": 0.0,
                            }
                        )
    return store


def merge_price_maps(*maps: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for m in maps:
        for k, tiers in m.items():
            slot = out.setdefault(k, {})
            for tier, vals in tiers.items():
                slot.setdefault(tier, {}).update(vals)
    return out


def pick_primary_pricing(tiers: dict) -> tuple[dict | None, dict]:
    """Return (pricing, extra_pricing_bits)."""
    extra: dict[str, Any] = {}
    primary = None
    for pref in ("global", "data_zone", "regional"):
        if pref in tiers and "input_per_1m" in tiers[pref]:
            primary = tiers[pref]
            break
    if primary is None:
        # any tier with input
        for tname, tvals in tiers.items():
            if "input_per_1m" in tvals and "long_context" not in tname:
                primary = tvals
                break
    if primary is None:
        for tname, tvals in tiers.items():
            if "input_per_1m" in tvals:
                primary = tvals
                break
    if primary is None:
        # image / special
        for tname, tvals in tiers.items():
            if tvals:
                primary = tvals
                break

    pricing = None
    if primary and "input_per_1m" in primary:
        pricing = {
            "input_per_1m": primary["input_per_1m"],
            "output_per_1m": primary.get("output_per_1m", 0.0),
            "currency": "USD",
        }
        if "cached_input_per_1m" in primary:
            pricing["cached_input_per_1m"] = primary["cached_input_per_1m"]

    # extras
    for tier_name in sorted(tiers.keys()):
        if tier_name == "global":
            continue
        if tier_name in tiers and tiers[tier_name]:
            extra[f"pricing_{tier_name}"] = {
                **{k: v for k, v in tiers[tier_name].items() if k != "context_note"},
                "currency": "USD",
            }
            if "context_note" in tiers[tier_name]:
                extra.setdefault("context_notes", {})[tier_name] = tiers[tier_name][
                    "context_note"
                ]
    if primary and primary.get("context_note"):
        extra.setdefault("context_notes", {})["primary"] = primary["context_note"]
    return pricing, extra


def split_modalities(val: Any) -> list[str]:
    if val is None:
        return ["text"]
    if isinstance(val, list):
        parts = [str(x).strip().lower() for x in val if str(x).strip()]
        return parts or ["text"]
    s = str(val).strip().lower()
    if not s or s in {"null", "none"}:
        return ["text"]
    parts = [p.strip() for p in re.split(r"[,/|]", s) if p.strip()]
    return parts or ["text"]


def provider_of(item: dict) -> str:
    scd = item.get("systemCatalogData") or {}
    tags = item.get("tags") or {}
    pub = (scd.get("publisher") or tags.get("author") or "").strip()
    if pub:
        key = pub.lower()
        if key in PUBLISHER_TO_PROVIDER:
            return PUBLISHER_TO_PROVIDER[key]
        # fuzzy
        for k, v in PUBLISHER_TO_PROVIDER.items():
            if k in key or key in k:
                return v
        return re.sub(r"[^a-z0-9]+", "-", key).strip("-") or "azure-foundry"
    ern = (item.get("entityResourceName") or "").lower()
    if ern in PUBLISHER_TO_PROVIDER:
        return PUBLISHER_TO_PROVIDER[ern]
    if ern:
        return re.sub(r"[^a-z0-9]+", "-", ern).strip("-")
    return "azure-foundry"


def lifecycle_of(item: dict) -> str:
    scd = item.get("systemCatalogData") or {}
    tags = item.get("tags") or {}
    stage = (item.get("stage") or "").strip()
    labels = item.get("labels") or []
    # retirement
    ret = (
        scd.get("inferenceRetirementDate")
        or tags.get("InferenceRetirementDate")
        or ""
    )
    dep = (
        scd.get("inferenceDeprecationDate")
        or tags.get("InferenceDeprecationDate")
        or ""
    )
    if ret:
        return "Retired"
    if dep:
        return "Deprecated"
    if scd.get("preview") or stage.lower() == "preview":
        return "Preview"
    if stage.lower() in {"generallyavailable", "ga", "production"}:
        return "GA"
    if "default" in labels or "latest" in labels:
        return "GA"
    return stage or ""


def azure_type_of(item: dict) -> str:
    scd = item.get("systemCatalogData") or {}
    tags = item.get("tags") or {}
    tasks = scd.get("inferenceTasks") or []
    if not tasks and tags.get("task"):
        tasks = [t.strip() for t in str(tags["task"]).split(",") if t.strip()]
    # Title-case join like existing "Chat completion,Responses"
    mapping = {
        "chat-completion": "Chat completion",
        "responses": "Responses",
        "completions": "Completions",
        "text-generation": "Text generation",
        "embeddings": "Embeddings",
        "image-generation": "Image generation",
        "image-text-to-image": "Image generation",
        "text-to-image": "Image generation",
        "audio": "Audio",
        "speech-to-text": "Speech to text",
        "text-to-speech": "Text to speech",
        "rerank": "Rerank",
    }
    pretty = []
    for t in tasks:
        pretty.append(mapping.get(t, t.replace("-", " ").capitalize()))
    return ",".join(pretty)


def is_maas_or_paygo(item: dict) -> bool:
    scd = item.get("systemCatalogData") or {}
    tags = item.get("tags") or {}
    deps = [str(x).lower() for x in (scd.get("deploymentTypes") or [])]
    offers = [str(x).lower() for x in (scd.get("azureOffers") or [])]
    dopts = str(tags.get("deploymentOptions") or "").lower()
    if any("maas" in d or "aoai" in d for d in deps):
        return True
    if any("paygo" in o or "ptu" in o for o in offers):
        return True
    if any(
        k in dopts
        for k in (
            "unifiedendpointmaas",
            "serverless",
            "aoai",
            "managed compute",
            "instant",
        )
    ):
        return True
    if scd.get("maasInference") or scd.get("enableMaap"):
        return True
    return False


def match_price_key(model_id: str, price_map: dict[str, dict]) -> str | None:
    """Map catalog model id to a price_map key. Reject empty keys; avoid loose substring traps."""

    def _valid(pk: str | None) -> str | None:
        if not pk:
            return None
        return pk if pk in price_map else None

    k = _norm_key(model_id)
    if not k:
        return None
    hit = _valid(k)
    if hit:
        return hit

    # provider/org prefixes (after _norm_key, "--" collapses to single "-")
    stripped = re.sub(
        r"^(meta-|deepseek-ai-|microsoft-|openai-|xai-|fireworks-?)",
        "",
        k,
    )
    if stripped and stripped != k:
        # re-apply alias table (e.g. deepseek-v3.2-speciale -> deepseek-v3.2-sp)
        stripped_n = _norm_key(stripped)
        hit = _valid(stripped_n) or _valid(stripped)
        if hit:
            return hit

    # slash form
    if "/" in model_id:
        k2 = _norm_key(model_id.split("/", 1)[1])
        hit = _valid(k2)
        if hit:
            return hit

    # FW-* : prefer dedicated fw-* keys (exact already tried); allow exact base only
    if k.startswith("fw-"):
        base = k[3:]
        hit = _valid(base)
        if hit:
            return hit
        # fw-glm-5.1 style already exact; do not fuzzy to sibling versions
        for suf in ("-instruct", "-chat", "-fp8", "-base"):
            if base.endswith(suf):
                hit = _valid(base[: -len(suf)])
                if hit:
                    return hit
        return None

    # strip common suffixes then exact (also try on prefix-stripped form)
    bases = [k]
    stripped2 = re.sub(
        r"^(meta-|deepseek-ai-|microsoft-|openai-|xai-|fireworks-?)",
        "",
        k,
    )
    if stripped2 and stripped2 not in bases:
        bases.append(_norm_key(stripped2))
        if stripped2 not in bases:
            bases.append(stripped2)
    for base in bases:
        cur = base
        for suf in (
            "-nim-microservice",
            "-onnx",
            "-instruct",
            "-chat",
            "-fp8",
            "-base",
            "-reasoning",
            "-non-reasoning",
        ):
            if cur.endswith(suf):
                cur = cur[: -len(suf)]
                hit = _valid(cur)
                if hit:
                    return hit

    # careful fuzzy: prefix with boundary; min length 6; no empty keys
    candidates: list[str] = []
    for pk in price_map:
        if not pk or len(pk) < 6:
            continue
        if k == pk:
            candidates.append(pk)
            continue
        if k.startswith(pk) and (len(k) == len(pk) or k[len(pk)] in "-."):
            candidates.append(pk)
            continue
        if pk.startswith(k) and (len(pk) == len(k) or pk[len(k)] in "-."):
            candidates.append(pk)
            continue
    if not candidates:
        return None
    candidates.sort(key=len, reverse=True)
    best = candidates[0]
    if k == best or best.startswith(k + "-") or best.startswith(k + "."):
        return best
    # k extends best
    if k.startswith(best + "-") or k.startswith(best + "."):
        rest = k[len(best) :].lstrip("-.")
        if rest in ("instruct", "chat", "fp8", "base", "reasoning", "non-reasoning", ""):
            return best
        # version-like or feature extension (multimodal/vision/mini) -> do not inherit
        return None
    return best


def build_entry(item: dict, price_map: dict[str, dict]) -> dict:
    scd = item.get("systemCatalogData") or {}
    tags = item.get("tags") or {}
    name = item.get("name") or "unknown"
    display = (
        item.get("displayName")
        or scd.get("displayName")
        or tags.get("summary")
        or name
    )
    provider = provider_of(item)

    in_mod = split_modalities(
        scd.get("inputModalities") or tags.get("inputModalities")
    )
    out_mod = split_modalities(
        scd.get("outputModalities") or tags.get("outputModalities")
    )

    ctx = scd.get("textContextWindow")
    max_out = scd.get("maxOutputTokens")
    nk = _norm_key(name)
    if (not ctx or not max_out) and nk in KNOWN_LIMITS:
        kctx, kout = KNOWN_LIMITS[nk]
        ctx = ctx or kctx
        max_out = max_out if max_out is not None else kout
    # limits object
    limits = item.get("limits") or {}
    if isinstance(limits, dict):
        ctx = ctx or limits.get("maxInputTokens") or limits.get("contextWindow")
        max_out = (
            max_out
            if max_out is not None
            else limits.get("maxOutputTokens") or limits.get("maxTokens")
        )

    tasks = scd.get("inferenceTasks") or []
    if not tasks and tags.get("task"):
        tasks = [t.strip() for t in str(tags["task"]).split(",") if t.strip()]
    tasks_l = [t.lower() for t in tasks]

    chat = any(t in tasks_l for t in ("chat-completion", "responses", "messages"))
    if not tasks_l:
        chat = True  # catalog already chat-filtered
    responses = "responses" in tasks_l
    vision = any(m in in_mod for m in ("image", "vision"))
    audio_in = any(m in in_mod for m in ("audio", "speech"))
    audio_out = any(m in out_mod for m in ("audio", "speech"))

    tool = scd.get("supportsToolCalling")
    if tool is None:
        caps = scd.get("modelCapabilities") or item.get("capabilities") or []
        if isinstance(caps, list):
            tool = any("tool" in str(c).lower() or "function" in str(c).lower() for c in caps)

    # reasoning heuristic
    reasoning = None
    nl = name.lower()
    if any(
        x in nl
        for x in (
            "o1",
            "o3",
            "o4",
            "reason",
            "r1",
            "thinking",
            "mythos",
            "opus",
            "gpt-5",
            "grok-3",
            "deepseek-r",
        )
    ):
        reasoning = True

    lifecycle = lifecycle_of(item)
    deprecated = lifecycle.lower() in {"retired", "deprecated"}

    # pricing
    pk = match_price_key(name, price_map)
    pricing = None
    extra: dict[str, Any] = {}
    if pk:
        pricing, price_extra = pick_primary_pricing(price_map[pk])
        extra.update(price_extra)
        extra["pricing_match_key"] = pk

    # deployment / offers into extra
    if scd.get("deploymentTypes"):
        extra["deployment_types"] = scd["deploymentTypes"]
    if scd.get("azureOffers"):
        extra["azure_offers"] = scd["azureOffers"]
    if tags.get("deploymentOptions"):
        extra["deployment_options"] = tags["deploymentOptions"]
    if scd.get("inferenceRetirementDate") or tags.get("InferenceRetirementDate"):
        extra["inference_retirement_date"] = scd.get("inferenceRetirementDate") or tags.get(
            "InferenceRetirementDate"
        )
    if scd.get("inferenceDeprecationDate") or tags.get("InferenceDeprecationDate"):
        extra["inference_deprecation_date"] = scd.get("inferenceDeprecationDate") or tags.get(
            "InferenceDeprecationDate"
        )
    if item.get("version"):
        extra["version"] = item["version"]
    if is_maas_or_paygo(item):
        extra["maas_or_paygo"] = True
    if scd.get("summary") or tags.get("summary"):
        extra["summary"] = (scd.get("summary") or tags.get("summary") or "")[:300]

    # long context from known / catalog
    if ctx and int(ctx) >= 200_000:
        extra["long_context"] = True
        extra["context_window"] = int(ctx)

    license_raw = (scd.get("license") or tags.get("license") or "").lower()
    if "mit" in license_raw:
        license_type = "open-source"
    elif "apache" in license_raw:
        license_type = "open-source"
    elif license_raw in {"custom", "proprietary"} or provider == "azure-openai":
        license_type = "api" if provider == "azure-openai" else "custom"
    elif license_raw:
        license_type = "custom"
    else:
        license_type = "api" if is_maas_or_paygo(item) else "open-source"

    row: dict[str, Any] = {
        "provider": provider,
        "model_id": name,
        "display_name": display if isinstance(display, str) else name,
        "context_window": int(ctx) if ctx else None,
        "max_output_tokens": int(max_out) if max_out not in (None, "") else None,
        "input_modalities": in_mod,
        "output_modalities": out_mod,
        "supports_chat_completion": bool(chat),
        "supports_function_calling": tool if tool is not None else None,
        "supports_json_mode": None,
        "supports_streaming": True if is_maas_or_paygo(item) else None,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "knowledge_cutoff": "",
        "azure_type": azure_type_of(item),
        "azure_lifecycle": lifecycle,
        "source": "azure_foundry",
        "supports_responses_api": responses,
        "license_type": license_type,
    }
    if audio_in:
        row["supports_audio_input"] = True
    if audio_out:
        row["supports_audio_output"] = True
    if deprecated:
        row["deprecated"] = True
    # aliases
    aliases = []
    if name != nk:
        aliases.append(nk)
    if provider and name:
        aliases.append(f"{provider}/{name}")
    # de-dupe
    seen: set[str] = set()
    aliases = [a for a in aliases if a and a != name and not (a in seen or seen.add(a))]
    if aliases:
        row["aliases"] = aliases

    if pricing:
        row["pricing"] = pricing
    if extra:
        row["extra"] = extra

    # drop null context if truly unknown — keep key as null for schema stability? existing uses int or missing
    if row["context_window"] is None:
        del row["context_window"]
    if row["max_output_tokens"] is None:
        del row["max_output_tokens"]

    return row


def load_price_map() -> dict[str, dict]:
    maps: list[dict[str, dict]] = []
    if PRICING.exists():
        raw = json.loads(PRICING.read_text(encoding="utf-8"))
        # AOAI full tables
        if "aoai" in raw and raw["aoai"].get("tables"):
            maps.append(parse_aoai_tables(raw["aoai"]["tables"]))
        for key in (
            "microsoft",
            "mistral",
            "llama",
            "cohere",
            "deepseek",
            "grok",
            "kimi",
            "fireworks",
            "bfl",
        ):
            if key in raw and raw[key].get("tables"):
                maps.append(parse_simple_token_tables(raw[key]["tables"]))
    if AOAI_PRICING.exists():
        raw2 = json.loads(AOAI_PRICING.read_text(encoding="utf-8"))
        maps.append(parse_aoai_tables(raw2.get("tables") or []))
    return merge_price_maps(*maps)


def main() -> None:
    if not CATALOG.exists():
        raise SystemExit(f"missing catalog scratch: {CATALOG}")

    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    items = cat.get("items") or []
    price_map = load_price_map()
    print(f"catalog items={len(items)} price_keys={len(price_map)}")
    print("price key sample:", sorted(price_map.keys())[:40])

    # Prefer richer API items over bare SSR cards when duplicate names
    by_name: dict[str, dict] = {}
    for it in items:
        name = it.get("name")
        if not name:
            continue
        prev = by_name.get(name)
        if prev is None:
            by_name[name] = it
            continue
        # prefer one with systemCatalogData
        if (it.get("systemCatalogData") or {}) and not (prev.get("systemCatalogData") or {}):
            by_name[name] = it
        elif len(json.dumps(it, default=str)) > len(json.dumps(prev, default=str)):
            by_name[name] = it

    models: list[dict] = []
    priced = 0
    maas = 0
    for name in sorted(by_name.keys(), key=str.lower):
        entry = build_entry(by_name[name], price_map)
        if entry.get("pricing"):
            priced += 1
        if (entry.get("extra") or {}).get("maas_or_paygo"):
            maas += 1
        models.append(entry)

    # Sort: maas/paygo first, then provider, model_id
    def sort_key(m: dict) -> tuple:
        return (
            0 if (m.get("extra") or {}).get("maas_or_paygo") else 1,
            0 if m.get("pricing") else 1,
            m.get("provider") or "",
            m.get("model_id") or "",
        )

    models.sort(key=sort_key)

    payload = {"models": models}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    OUT.write_text(text, encoding="utf-8")
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(OUT, INSTALLED)

    # stats
    from collections import Counter

    pubs = Counter(m.get("provider") for m in models)
    extra_n = sum(1 for m in models if m.get("extra"))
    print(f"wrote n={len(models)} priced={priced} maas={maas} extra={extra_n}")
    print("providers", pubs.most_common(20))
    print(f"OUT -> {OUT}")
    print(f"INSTALLED -> {INSTALLED}")

    # log
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    log_entry = f"""
## azure_foundry — {ts}

- Catalog: chat-completion filter via Playwright paginate (`_scratch_azure_catalog_raw.json`, n={len(items)} unique names={len(by_name)})
- Pricing: AOAI + Foundry partner pages (`_scratch_azure_pricing_tables.json`), price_keys={len(price_map)}
- Output: n={len(models)} priced={priced} maas_or_paygo={maas} extra={extra_n}
- Providers (top): {", ".join(f"{k}={v}" for k, v in pubs.most_common(12))}
- Sources: {SOURCE_CATALOG} ; {SOURCE_AOAI} ; {SOURCE_FOUNDRY_MODELS}*
- Script: `scripts/_update_azure_foundry.py` (+ `scripts/_scrape_azure_foundry_full.py`)
- Installed copy: `{INSTALLED}`
"""
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else "# Provider update log\n"
    if not prev.endswith("\n"):
        prev += "\n"
    LOG.write_text(prev + log_entry, encoding="utf-8")
    print("logged ->", LOG)


if __name__ == "__main__":
    main()
