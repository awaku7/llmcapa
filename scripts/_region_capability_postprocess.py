"""Apply scraped regional availability to the bundled catalogs.

Region data comes from the providers' official documentation pages:

- Amazon Bedrock: ``_scrape_amazon_regions.fetch_bedrock_regions``
- Vertex AI: ``_scrape_vertex_regions.fetch_vertex_regions``
- Azure Foundry: ``_scrape_azure_regions.fetch_azure_regions``

Run directly to refresh all three catalogs in place:

    python scripts/_region_capability_postprocess.py

Only models the official pages list are touched; records without a
``regions`` entry keep whatever they already carry.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llmcapa._catalog_format import dump_catalog

try:
    from scripts._scrape_amazon_regions import fetch_bedrock_regions
    from scripts._scrape_azure_regions import fetch_azure_regions
    from scripts._scrape_vertex_regions import fetch_vertex_regions
except ModuleNotFoundError:  # Running directly from the scripts directory.
    from _scrape_amazon_regions import fetch_bedrock_regions
    from _scrape_azure_regions import fetch_azure_regions
    from _scrape_vertex_regions import fetch_vertex_regions

DATA = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"


def apply_regions(models: list[dict], scraped: dict[str, dict]) -> int:
    """Write scraped ``regions`` into matching catalog records."""
    count = 0
    for model in models:
        regions = scraped.get(model.get("model_id"))
        if regions is None:
            continue
        model["regions"] = regions
        count += 1
    return count


def _refresh(filename: str, scraped: dict[str, dict]) -> int:
    path = DATA / filename
    payload = json.loads(path.read_bytes().decode("utf-8"))
    count = apply_regions(payload["models"], scraped)
    path.write_bytes(dump_catalog(payload).encode("utf-8"))
    return count


def main() -> None:
    checked_at = datetime.now(timezone.utc).date().isoformat()
    bedrock = fetch_bedrock_regions(checked_at)
    print(
        f"amazon.json: { _refresh('amazon.json', bedrock) } models updated "
        f"with Bedrock regional availability"
    )
    vertex = fetch_vertex_regions(checked_at)
    print(
        f"vertex-ai.json: { _refresh('vertex-ai.json', vertex) } models updated "
        f"with Vertex AI endpoint locations"
    )
    azure = fetch_azure_regions(checked_at)
    print(
        f"azure_foundry.json: { _refresh('azure_foundry.json', azure) } models "
        f"updated with Azure Foundry regional availability"
    )


if __name__ == "__main__":
    main()
