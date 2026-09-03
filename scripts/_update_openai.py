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

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "openai.json"
MODELS_URL = "https://developers.openai.com/api/docs/models.md"
PRICING_URL = "https://developers.openai.com/api/docs/pricing.md"
BASE = "https://developers.openai.com"
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
    entry["supports_reasoning"] = (
        "reasoning token support" in text.lower() or "reasoning" in features
    )
    cutoff = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4}) knowledge cutoff", text)
    if cutoff:
        entry["knowledge_cutoff"] = cutoff.group(1)
    return entry


def prices(markdown: str) -> dict[str, tuple[float, float]]:
    result = {}
    for row in re.findall(
        r"^\|\s*([^|]+?)\s*\|\s*\$?([\d.]+)[^|]*\|[^|]*\|\s*[^|]*\|\s*\$?([\d.]+)",
        markdown,
        re.MULTILINE,
    ):
        result[row[0].strip()] = (float(row[1]), float(row[2]))
    return result


def main() -> None:
    index = fetch(MODELS_URL)
    pricing = prices(fetch(PRICING_URL).split("### Batch pricing data", 1)[0])
    links = re.findall(
        r"^- \[[^\]]+\]\((/api/docs/models/[^)]+\.md)\)", index, re.MULTILINE
    )
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
        # Preserve library-specific metadata unless the official page replaces it.
        if mid in current_by_id:
            old = current_by_id[mid]
            merged = dict(old)
            merged.update(entry)
            merged["extra"] = {**old.get("extra", {}), **entry.get("extra", {})}
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
            entry["pricing"] = {
                "input_per_1m": None,
                "output_per_1m": None,
                "currency": "USD",
            }
        updated.append(entry)
        seen.add(mid)
    for old in current.get("models", []):
        if old.get("model_id") not in seen:
            updated.append(old)
    updated.sort(key=lambda x: x.get("model_id", ""))
    payload = json.dumps({"models": updated}, ensure_ascii=False, indent=2) + "\n"
    DATA.write_bytes(payload.replace("\n", "\r\n").encode("utf-8"))
    with (ROOT / "provider_update_log.md").open("a", encoding="utf-8", newline="") as f:
        f.write(
            f"\r\n## OpenAI ({datetime.now(timezone.utc).date():%Y-%m-%d})\r\n\r\n- Source: {MODELS_URL}\r\n- Source: {PRICING_URL}\r\n- Dynamically discovered {len(seen)} official model pages; legacy records preserved: {len(updated)-len(seen)}\r\n"
        )
    print(f"openai.json: {len(updated)} models; discovered {len(seen)} official models")


if __name__ == "__main__":
    main()
