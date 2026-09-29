"""Refresh SiliconFlow model metadata from its public official documentation.

The authenticated ``GET /v1/models`` endpoint is not used. The updater reads
SiliconFlow's public Markdown documentation and extracts model IDs only from
explicit ``model=`` examples and supported-model lists. Documentation pages do
not expose a complete live catalog, so prior well-formed records not found in
this pass are retained and marked unconfirmed rather than deleted.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/siliconflow.json"
LOG = ROOT / "provider_update_log.md"
BASE_URL = "https://api.siliconflow.com/v1"
QUICKSTART = "https://docs.siliconflow.com/en/userguide/quickstart.md"

# These public, provider-owned pages contain examples or explicit supported
# model lists. The account-only Models page is intentionally not scraped.
DOC_PAGES = {
    "quickstart": (QUICKSTART, "text"),
    "text_generation": (
        "https://docs.siliconflow.com/en/userguide/capabilities/text-generation.md",
        "text",
    ),
    "vision": (
        "https://docs.siliconflow.com/en/userguide/capabilities/vision.md",
        "vision",
    ),
    "image_generation": (
        "https://docs.siliconflow.com/en/userguide/capabilities/images.md",
        "image_generation",
    ),
    "video_generation": (
        "https://docs.siliconflow.com/en/userguide/capabilities/video.md",
        "video_generation",
    ),
    "text_to_speech": (
        "https://docs.siliconflow.com/en/userguide/capabilities/text-to-speech.md",
        "audio_generation",
    ),
    "reasoning": (
        "https://docs.siliconflow.com/en/userguide/capabilities/reasoning.md",
        "reasoning",
    ),
}

MODEL_ASSIGNMENT_RE = re.compile(
    r"(?i)\bmodel\s*(?:=|:)\s*[\"'`]([^\"'`]+)[\"'`]"
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")
SUPPORTED_HEADING_RE = re.compile(r"\bsupported\s+models?\b|\bmodel\s+list\b", re.I)
MODEL_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")


def clean_model_id(value: str) -> str | None:
    """Return a plausible model identifier, rejecting prose and page markup."""
    candidate = value.strip().strip("`*_\"'.,;:()[]{}<>")
    if not 3 <= len(candidate) <= 128:
        return None
    if not MODEL_ID_RE.fullmatch(candidate) or not any(ch.isdigit() for ch in candidate):
        return None
    if candidate.startswith(("/", ".")) or candidate.endswith(("/", ".")):
        return None
    if "//" in candidate or ".." in candidate:
        return None
    return candidate


def extract_supported_list_ids(markdown: str) -> set[str]:
    """Extract IDs only from Markdown sections explicitly titled as model lists."""
    found: set[str] = set()
    section_level: int | None = None

    for line in markdown.splitlines():
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            title = re.sub(r"^\d+(?:\.\d+)*\s+", "", heading.group(2)).strip()
            if section_level is not None and level <= section_level:
                section_level = None
            if section_level is None and SUPPORTED_HEADING_RE.search(title):
                section_level = level
                continue
            if section_level is not None and level > section_level:
                item = re.sub(r"[*`]", "", title).strip()
                token = item.split(maxsplit=1)[0] if item else ""
                model_id = clean_model_id(token)
                if model_id:
                    found.add(model_id)
            continue

        if section_level is None:
            continue
        item = LIST_ITEM_RE.match(line)
        if not item:
            continue
        text = re.sub(r"[*`]", "", item.group(1)).strip()
        # Series/category labels such as ``DeepseekVL2 Series:`` are not IDs.
        if text.endswith(":"):
            continue
        token = text.split(maxsplit=1)[0] if text else ""
        model_id = clean_model_id(token)
        if model_id:
            found.add(model_id)

    return found


def extract_model_ids(markdown: str) -> set[str]:
    """Extract IDs in explicit API model fields and supported-model lists."""
    found = extract_supported_list_ids(markdown)
    for match in MODEL_ASSIGNMENT_RE.finditer(markdown):
        model_id = clean_model_id(match.group(1))
        if model_id:
            found.add(model_id)
    return found


def fetch_markdown(url: str) -> str:
    request = Request(
        url,
        headers={
            "Accept": "text/markdown,text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": "llmcapa-official-docs-scraper/1.0",
        },
    )
    with urlopen(request, timeout=45) as response:
        body = response.read(2_000_000)
        content_type = response.headers.get("Content-Type", "").lower()
    text = body.decode("utf-8", "replace")
    if not text.strip() or "text/html" in content_type and "# " not in text[:2000]:
        raise RuntimeError(f"official documentation did not return Markdown: {url}")
    return text


def scrape_documentation() -> dict[str, dict[str, set[str]]]:
    """Return model IDs and the documentation categories that mention them."""
    evidence: dict[str, dict[str, set[str]]] = {}
    for page_name, (url, category) in DOC_PAGES.items():
        try:
            markdown = fetch_markdown(url)
        except Exception as exc:  # noqa: BLE001
            print(f"warning: could not scrape {page_name}: {exc}", flush=True)
            continue
        for model_id in extract_model_ids(markdown):
            key = model_id.casefold()
            entry = evidence.setdefault(
                key, {"model_id": set(), "categories": set(), "pages": set()}
            )
            entry["model_id"].add(model_id)
            entry["categories"].add(category)
            entry["pages"].add(url.removesuffix(".md"))
    if len(evidence) < 5:
        raise RuntimeError(
            f"official documentation scrape found only {len(evidence)} model IDs; refusing to refresh"
        )
    return evidence


def _ordered_modalities(values: set[str]) -> list[str]:
    order = ("text", "image", "audio", "video", "embedding", "rerank")
    return [modality for modality in order if modality in values]


def build_live_rows(evidence: dict[str, dict[str, set[str]]]) -> list[dict]:
    rows = []
    checked_at = datetime.now(timezone.utc).date().isoformat()
    for key in sorted(evidence):
        item = evidence[key]
        model_id = sorted(item["model_id"], key=str.casefold)[0]
        categories = item["categories"]
        input_modalities: set[str] = set()
        output_modalities: set[str] = set()

        if categories.intersection({"text", "vision", "reasoning"}):
            input_modalities.add("text")
            output_modalities.add("text")
        if "vision" in categories:
            input_modalities.add("image")
        if "image_generation" in categories:
            input_modalities.add("text")
            output_modalities.add("image")
        if "video_generation" in categories:
            input_modalities.add("text")
            output_modalities.add("video")
            if "-i2v-" in model_id.casefold():
                input_modalities.add("image")
        if "audio_generation" in categories:
            input_modalities.add("text")
            output_modalities.add("audio")

        chat_evidence = categories.intersection({"text", "vision", "reasoning"})
        generation_evidence = categories.intersection(
            {"image_generation", "video_generation", "audio_generation"}
        )
        supports_chat = True if chat_evidence else (False if generation_evidence else None)
        source_pages = sorted(item["pages"])
        rows.append(
            {
                "provider": "siliconflow",
                "model_id": model_id,
                "display_name": model_id,
                "context_window": 0,
                "max_output_tokens": 0,
                "input_modalities": _ordered_modalities(input_modalities),
                "output_modalities": _ordered_modalities(output_modalities),
                "supports_chat_completion": supports_chat,
                "supports_function_calling": None,
                "supports_json_mode": None,
                "supports_streaming": None,
                "supports_vision": True if "vision" in categories else None,
                "supports_reasoning": True if "reasoning" in categories else None,
                "supports_responses_api": None,
                "pricing": None,
                "deprecated": False,
                "aliases": [],
                "license_type": "api",
                "extra": {
                    "source": source_pages[0],
                    "source_type": "official_docs_scrape",
                    "spec_status": "documented_example_or_supported_list",
                    "evidence_pages": source_pages,
                    "evidence_categories": sorted(categories),
                    "checked_at": checked_at,
                    "endpoints": [
                        {
                            "base_url": BASE_URL,
                            "protocol": "openai-compatible",
                            "auth": "bearer",
                            "source": QUICKSTART.removesuffix(".md"),
                        }
                    ],
                },
            }
        )
    return rows


def is_plausible_previous_id(value: object) -> bool:
    """Filter obvious HTML/MDX property fragments from the former broad scrape."""
    candidate = str(value or "")
    return clean_model_id(candidate) is not None


def merge_previous(live: list[dict], previous: list[dict]) -> list[dict]:
    """Keep useful exact-ID metadata and plausible historical rows, not page junk."""
    previous_by_id = {
        str(row.get("model_id", "")).casefold(): row
        for row in previous
        if isinstance(row, dict) and row.get("model_id")
    }
    live_keys = {str(row["model_id"]).casefold() for row in live}
    live_basenames = {key.rsplit("/", 1)[-1] for key in live_keys}
    result = []

    for fresh in live:
        key = fresh["model_id"].casefold()
        old = previous_by_id.get(key)
        if old:
            merged = dict(old)
            merged.update(fresh)
            merged_extra = dict(old.get("extra") or {})
            merged_extra.update(fresh.get("extra") or {})
            merged["extra"] = merged_extra
            for field in ("context_window", "max_output_tokens", "pricing"):
                if fresh.get(field) in (None, 0) and old.get(field) not in (None, 0):
                    merged[field] = old[field]
            result.append(merged)
        else:
            result.append(fresh)

    preserved = 0
    for old in previous:
        if not isinstance(old, dict):
            continue
        model_id = str(old.get("model_id", ""))
        key = model_id.casefold()
        if (
            not is_plausible_previous_id(model_id)
            or key in live_keys
            or key.rsplit("/", 1)[-1] in live_basenames
        ):
            continue
        row = dict(old)
        extra = dict(row.get("extra") or {})
        extra["not_confirmed_by_current_public_docs"] = True
        row["extra"] = extra
        result.append(row)
        preserved += 1

    result.sort(key=lambda row: str(row.get("model_id", "")).casefold())
    print(f"SiliconFlow documented IDs: {len(live)}; plausible prior-only records retained: {preserved}")
    return result


def update_catalog() -> int:
    evidence = scrape_documentation()
    live = build_live_rows(evidence)
    current = json.loads(DATA.read_text(encoding="utf-8"))
    previous = current.get("models") or []
    models = merge_previous(live, previous)
    DATA.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    checked_at = datetime.now(timezone.utc).date().isoformat()
    source_lines = "\n".join(
        f"- {name}: {url.removesuffix('.md')}"
        for name, (url, _category) in DOC_PAGES.items()
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## SiliconFlow public documentation scrape ({checked_at})\n\n"
        + f"- Extracted {len(live)} documented model IDs; no API key or model-list API was used.\n"
        + "- Evidence pages:\n"
        + source_lines
        + "\n- Malformed model-like fragments from prior broad HTML scraping were discarded.\n",
        encoding="utf-8",
    )
    print(f"siliconflow.json: scraped IDs={len(live)} total records={len(models)}")
    return len(live)


def main() -> None:
    update_catalog()


if __name__ == "__main__":
    main()
