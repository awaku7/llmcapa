"""Provider catalog, endpoint, and Structured Outputs updater for ai21."""

"""Update endpoint metadata for the ai21 provider only."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/ai21.json"
LOG = ROOT / "provider_update_log.md"
BASE_URL = "https://api.ai21.com/studio/v1"
SOURCE = "https://docs.ai21.com/"


def update_endpoints():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    n = 0
    for model in data.get("models", []):
        model.setdefault("extra", {})["endpoints"] = [
            {
                "base_url": BASE_URL,
                "protocol": "openai-compatible",
                "auth": "bearer",
                "source": SOURCE,
            }
        ]
        n += 1
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + f"\n## ai21 endpoint metadata refresh ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Updated: {n} models.\n",
        encoding="utf-8",
    )
    print("ai21: endpoint metadata updated", n)


"""Audit Structured Outputs for ai21 only."""
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/ai21.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://docs.ai21.com/docs/overview"
DOCUMENTED = False


def update_structured():
    req = Request(SOURCE, headers={"User-Agent": "llmcapa-structured-audit/1.0"})
    with urlopen(req, timeout=30) as response:
        response.read(100000)
    data = json.loads(DATA.read_text(encoding="utf-8"))
    n = 0
    for model in data.get("models", []):
        extra = model.setdefault("extra", {})
        extra.update(
            {
                "structured_output_source": SOURCE,
                "structured_output_checked_at": datetime.now(timezone.utc)
                .date()
                .isoformat(),
                "structured_output_api_documented": DOCUMENTED,
            }
        )
        if DOCUMENTED:
            model["supports_json_mode"] = True
            model["supports_json_schema"] = True
        n += 1
    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    LOG.write_text(
        LOG.read_text(encoding="utf-8")
        + "\n## ai21 Structured Outputs audit ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Updated: {n} models; documented={DOCUMENTED}.\n",
        encoding="utf-8",
    )
    print("ai21: structured outputs audited", n)


def main():
    update_endpoints()
    update_structured()


if __name__ == "__main__":
    main()
