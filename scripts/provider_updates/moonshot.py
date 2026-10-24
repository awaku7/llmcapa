"""Update endpoint metadata for the moonshot provider only."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "src/llmcapa/data/moonshot.json"
BASE_URL = "https://api.moonshot.cn/v1"
SOURCE = "https://platform.moonshot.cn/docs/"


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
    print("moonshot: endpoint metadata updated", n)


if __name__ == "__main__":
    main()
