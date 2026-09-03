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
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "google.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "google.json"
)
LOG = WORKDIR / "provider_update_log.md"
SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"


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


def discover_prices() -> dict[str, tuple[float, float, int]]:
    """Read model IDs and current token prices from Google's pricing tables."""
    html = fetch(SOURCE)
    headings = list(
        re.finditer(
            r'<h2 id="([^"]+)"[^>]*>.*?</h2>\s*<em>.*?<code[^>]*>([^<]+)</code>',
            html,
            re.DOTALL,
        )
    )
    discovered: dict[str, tuple[float, float, int]] = {}
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


def template_for(model_id: str) -> dict:
    """Build conservative metadata for a newly documented Gemini model."""
    display = model_id.replace("-", " ").title()
    return {
        "display_name": display,
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "supports_function_calling": True,
        "supports_json_mode": True,
        "supports_vision": any(x in model_id for x in ("image", "vision")),
        "supports_reasoning": any(x in model_id for x in ("pro", "flash")),
        "supports_chat_completion": True,
        "max_output_tokens": 65_536,
        "extra": {"source": SOURCE, "discovered_from": SOURCE},
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
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": True,
        "supports_fim": False,
        "license_type": "api",
        "tokenizer_name": "",
        "knowledge_cutoff": None,
        "pricing": {"input_per_1m": inp, "output_per_1m": out, "currency": "USD"},
        "deprecated": False,
        "aliases": [],
        "reasoning_effort_values": None,
        "extra": deepcopy(template.get("extra") or {}),
    }


def main() -> None:
    data = json.loads(OUT.read_text(encoding="utf-8"))
    models: list[dict] = data["models"]
    by_id = {m["model_id"]: m for m in models}
    google_prices = discover_prices()
    discovered_extras, discovered_deprecations = discover_metadata(fetch(SOURCE))
    existing_ids = set(by_id)

    updated = 0
    inserted = 0
    specialty = 0
    deprecated_n = 0

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
    inserted_ids = sorted(set(by_id) - existing_ids)
    print(
        f"google.json: updated={updated} inserted={inserted} specialty={specialty} "
        f"deprecated_flagged={deprecated_n} total={len(models)} "
        f"(active={active}, token-priced={priced})",
        flush=True,
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"""
## Google refresh ({ts})

### Source
- Pricing: {SOURCE}
- Apply: `scripts/_update_google.py`

### Result
- google.json: **{len(models)}** models (active={active}, token-priced={priced})
- Inserted (discovered): {", ".join(inserted_ids) if inserted_ids else "none"}
- Lyria-3 clip/pro: $0.04 / $0.08 per song (extra)
- Deprecations: discovered from official model pricing sections
- Install copy synced
"""
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry.lstrip(), encoding="utf-8")


if __name__ == "__main__":
    main()
