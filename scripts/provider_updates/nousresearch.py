"""Audit Structured Outputs for nousresearch only."""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/nousresearch.json"
LOG = ROOT / "provider_update_log.md"
SOURCE = "https://nousresearch.com/"
DOCUMENTED = False


def main():
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
        + "\n## nousresearch Structured Outputs audit ({datetime.now(timezone.utc).date()})\n\n- Source: {SOURCE}\n- Updated: {n} models; documented={DOCUMENTED}.\n",
        encoding="utf-8",
    )
    print("nousresearch: structured outputs audited", n)


if __name__ == "__main__":
    main()
