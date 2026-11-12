"""Generate or check the tracked SQLite catalog on a developer PC."""

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate without writing")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    from llmcapa._catalog_db import build_catalog, check_catalog

    database = root / "src" / "llmcapa" / "data" / "catalog.sqlite3"
    if args.check:
        check_catalog(database)
    else:
        build_catalog(database)
    print(f"SQLite catalog OK: {database} ({database.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
