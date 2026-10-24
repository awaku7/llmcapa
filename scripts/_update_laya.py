"""Refresh Laya's published package and Hugging Face checkpoint metadata.

Laya's official repository describes three typed-decision checkpoints but
there is no machine-readable capability catalog. This updater therefore
refreshes only the PyPI version and official Hugging Face inventory. It never
infers model capabilities or creates records for new checkpoints automatically.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "laya.json"
PACKAGE_URL = "https://pypi.org/pypi/laya/json"
HF_ORG = "convaiinnovations"
HF_API_URL = (
    f"https://huggingface.co/api/models?author={quote(HF_ORG)}&limit=100&full=false"
)
SOURCE = "https://github.com/NandhaKishorM/laya"


def _fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "llmcapa-provider-updater/1.0"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read(2_000_000).decode("utf-8", "replace"))


def parse_package_version(payload: object) -> str:
    if not isinstance(payload, dict):
        raise TypeError("PyPI returned a non-object package response")
    info = payload.get("info")
    version = info.get("version") if isinstance(info, dict) else None
    if not isinstance(version, str) or not version.strip():
        raise ValueError("PyPI response is missing info.version")
    return version.strip()


def parse_hf_model_ids(payload: object) -> set[str]:
    if not isinstance(payload, list):
        raise TypeError("Hugging Face returned a non-list organization response")
    # The publisher owns many other Hugging Face projects. Only repositories
    # named as Laya checkpoints belong in this provider catalog.
    model_ids = {
        str(item["modelId"]).strip()
        for item in payload
        if isinstance(item, dict)
        and item.get("modelId")
        and str(item["modelId"]).rsplit("/", 1)[-1].casefold().startswith("laya")
    }
    if not model_ids:
        raise ValueError("Hugging Face organization response contained no models")
    return model_ids


def update_catalog(
    package_version: str, hf_model_ids: set[str], *, checked_at: str | None = None
) -> tuple[int, list[str]]:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("laya.json has no model records")

    checked_at = checked_at or datetime.now(timezone.utc).date().isoformat()
    known_hf_ids: set[str] = set()
    changed = 0
    for model in models:
        if not isinstance(model, dict) or model.get("provider") != "laya":
            continue
        extra = model.setdefault("extra", {})
        repo = str(extra.get("huggingface_model", "")).strip()
        if repo:
            known_hf_ids.add(repo)
        before = dict(extra)
        extra.update(
            {
                "official_source": SOURCE,
                "official_source_checked_at": checked_at,
                "pypi": "https://pypi.org/project/laya/",
                "package_version_checked": package_version,
                "official_hf_org": HF_ORG,
                "official_hf_models_sample": sorted(hf_model_ids),
                "official_hf_model_available": repo in hf_model_ids if repo else None,
            }
        )
        decision = model.get("decision")
        if isinstance(decision, dict):
            decision.setdefault("extra", {})["checked_at"] = checked_at
        changed += extra != before

    if not changed:
        return 0, sorted(hf_model_ids - known_hf_ids)

    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    unregistered = sorted(hf_model_ids - known_hf_ids)
    print(
        f"laya.json: refreshed metadata for {changed} records; version={package_version}"
    )
    return changed, unregistered


def main() -> None:
    # Fetch and validate every source before touching the catalog.
    version = parse_package_version(_fetch_json(PACKAGE_URL))
    model_ids = parse_hf_model_ids(_fetch_json(HF_API_URL))
    update_catalog(version, model_ids)


if __name__ == "__main__":
    main()
