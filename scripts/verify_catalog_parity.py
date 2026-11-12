"""Verify full bundled JSON/SQLite catalog parity without modifying data."""

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from llmcapa._catalog_parity import verify_catalog

    counts = verify_catalog()
    for name, count in counts.items():
        print(f"{name}: {count:,}")
    print("JSON/SQLite catalog parity OK")


if __name__ == "__main__":
    main()
