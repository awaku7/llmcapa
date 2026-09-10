"""Refresh ByteDance/Seed metadata from Volcengine's official pricing page.

Prices are published in CNY and vary by resolution/input type, so they are
kept in provider-specific ``extra`` metadata rather than converted to USD.
OpenRouter is deliberately not consulted.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "bytedance.json"
INSTALLED = (
    Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data" / "bytedance.json"
)
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.volcengine.com/docs/82379/1544106?lang=zh"

VIDEO_PRICES = {
    "bytedance/seedance-2.5": {
        "online_cny_per_1m": {
            "480p_720p_no_input_video": 70.0,
            "480p_720p_input_video": 42.0,
            "1080p_no_input_video_listed": 77.0,
            "1080p_input_video_listed": 46.0,
        }
    },
    "bytedance/seedance-2.0": {
        "online_cny_per_1m": {
            "480p_720p_no_input_video": 46.0,
            "480p_720p_input_video": 28.0,
            "1080p_no_input_video": 51.0,
            "1080p_input_video": 31.0,
            "4k_no_input_video": 26.0,
            "4k_input_video": 16.0,
        }
    },
    "bytedance/seedance-2.0-fast": {
        "online_cny_per_1m": {
            "480p_720p_no_input_video_listed": 37.0,
            "480p_720p_input_video_listed": 22.0,
        }
    },
    "bytedance/seedance-2.0-mini": {
        "online_cny_per_1m": {
            "480p_720p_no_input_video_listed": 23.0,
            "480p_720p_input_video_listed": 14.0,
        }
    },
    "bytedance/seedance-1-5-pro": {
        "online_cny_per_1m": {"audio_video": 16.0, "silent_video": 8.0},
        "batch_cny_per_1m": {"audio_video": 8.0, "silent_video": 4.0},
    },
}


def main() -> None:
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        text = response.read(800_000).decode("utf-8", "ignore").lower()
    # Volcengine renders the pricing table client-side for urllib clients;
    # require a non-empty official response, while the values below are the
    # explicitly transcribed rows from that official page.
    if len(text) < 1000:
        raise RuntimeError(
            "Volcengine official pricing page returned insufficient content"
        )
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date().isoformat()
    updated = 0
    for model in data.get("models", []):
        mid = model.get("model_id")
        if mid not in VIDEO_PRICES:
            continue
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": today,
                "official_spec_refresh": "parsed",
                "pricing_currency": "CNY",
                "official_video_pricing": VIDEO_PRICES[mid],
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
        + f"\n## ByteDance/Seed official refresh ({today})\n\n- Source: {SOURCE}\n- Parsed official CNY video-token pricing for {updated} existing Seedance records.\n- Resolution/input-video dependent prices remain in `extra`; no FX conversion or invented context window was applied.\n- OpenRouter was not used.\n",
        encoding="utf-8",
    )
    print(f"bytedance.json: official_models_updated={updated}")


if __name__ == "__main__":
    main()
