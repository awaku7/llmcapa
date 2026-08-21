"""Refresh small-provider model availability from official Hugging Face APIs.

This is deliberately separate from the Hugging Face popularity catalog and
never reads OpenRouter. It records only model IDs exposed by each provider's
official organization page; capability/price fields are not inferred.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
INSTALLED = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"
LOG = ROOT / "provider_update_log.md"
ORGS = {
    "anthracite-org": "anthracite-org", "cognitivecomputations": "cognitivecomputations",
    "deepcogito": "deepcogito", "gryphe": "Gryphe", "inclusionai": "inclusionAI",
    "kwaipilot": "Kwai-Kolors", "mancer": "Mancer", "meituan": "meituan-longcat",
    "nex-agi": "Nex-AGI", "perceptron": "PERCEPTRON", "sao10k": "Sao10K",
    "thedrummer": "TheDrummer", "undi95": "undi95",
}


def fetch_models(org: str) -> list[str]:
    url = f"https://huggingface.co/api/models?author={quote(org)}&limit=100&full=false"
    req = Request(url, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=30) as response:
        payload = json.loads(response.read(500_000).decode("utf-8", "ignore"))
    return sorted({item["modelId"] for item in payload if isinstance(item, dict) and item.get("modelId")})


def main() -> None:
    today = date.today().isoformat()
    results = []
    for provider, org in ORGS.items():
        try:
            models = fetch_models(org)
            if not models:
                results.append((provider, 0, "empty"))
                continue
            path = DATA / f"{provider}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            changed = 0
            for model in data.get("models", []):
                extra = model.setdefault("extra", {})
                before = dict(extra)
                extra.update({"official_source": f"https://huggingface.co/{org}", "official_source_checked_at": today, "official_spec_refresh": "parsed_catalog_only", "official_hf_org": org, "official_hf_model_count": len(models), "official_hf_models_sample": models[:100]})
                changed += extra != before
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            target = INSTALLED / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            results.append((provider, changed, "updated"))
        except Exception as exc:
            results.append((provider, 0, f"failed: {exc}"))
    lines = [f"\n## Hugging Face official organization refresh ({today})\n", "", "- Source: official Hugging Face organization APIs (`huggingface.co/api/models`).", "- Recorded provider organization model catalogs only; no prices or capabilities were inferred.", "- OpenRouter was not used.", ""]
    lines.extend(f"- {provider}: {count} record(s), {status}" for provider, count, status in results)
    LOG.write_text(LOG.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")
    print("; ".join(f"{p}={n}:{s}" for p, n, s in results))

if __name__ == "__main__": main()
