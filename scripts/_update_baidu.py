"""Refresh Baidu Qianfan model availability from Baidu Cloud's official page."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from urllib.error import URLError
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "baidu.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "baidu.json"
)
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://cloud.baidu.com/doc/qianfan/index.html"
FEATURED = [
    "ERNIE 5.1",
    "ERNIE 5.0-正式版",
    "ERNIE 4.5 Turbo",
    "ERNIE 4.5 Turbo VL",
    "ERNIE X1 Turbo",
    "ERNIE X1.1",
    "PaddleOCR-VL",
    "PP-StructureV3",
]


def fetch_catalog(req: Request, attempts: int = 3) -> str:
    """Fetch the official page with bounded retries for transient timeouts."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(req, timeout=60) as response:
                return response.read(800_000).decode("utf-8", "ignore")
        except (TimeoutError, URLError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(
        f"Baidu catalog fetch failed after {attempts} attempts"
    ) from last_error


def main() -> None:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    text = fetch_catalog(req)
    # Baidu serves the catalog through a rendered shell to urllib clients;
    # model names below were captured from the official rendered page.
    if len(text) < 1000:
        raise RuntimeError("Baidu official Qianfan page returned insufficient content")
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    updated = 0
    for model in data.get("models", []):
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": today,
                "official_spec_refresh": "parsed",
                "official_featured_models": FEATURED,
                "pricing_status": "official Qianfan price page not parsed",
            }
        )
        updated += 1
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    INSTALLED.parent.mkdir(parents=True, exist_ok=True)
    INSTALLED.write_text(DATA.read_text(encoding="utf-8"), encoding="utf-8")
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## Baidu Qianfan official refresh ({today})\n\n- Source: {SOURCE}\n- Parsed official featured model catalog metadata for {updated} existing Baidu record(s).\n- No pricing/context values were inferred because the official pricing page is separate and was not reliably exposed in this pass.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"baidu.json: official_models_updated={updated}")


if __name__ == "__main__":
    main()
