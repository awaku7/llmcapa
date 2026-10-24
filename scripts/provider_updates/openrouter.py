"""Update endpoint metadata for the openrouter provider only."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/openrouter.json"
BASE_URL = "https://openrouter.ai/api/v1"
SOURCE = "https://openrouter.ai/docs/api-reference/overview"


def main():
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
    print("openrouter: endpoint metadata updated", n)


if __name__ == "__main__":
    main()
