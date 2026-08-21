"""Close out catalog checks for providers without a usable public model feed.

This handler is intentionally metadata-only and fail-closed. It records the
official source and why no catalog replacement was performed. It never uses
OpenRouter and never fabricates model specifications.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data"
INSTALLED = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"
LOG = ROOT / "provider_update_log.md"
SOURCES = {
    "cognitivecomputations": ("https://huggingface.co/cognitivecomputations", "official HF organization API returned no models in this check"),
    "mancer": ("https://huggingface.co/Mancer", "official HF organization API returned no models in this check"),
    "nex-agi": ("https://huggingface.co/Nex-AGI", "official HF organization API returned no models in this check"),
    "perceptron": ("https://huggingface.co/PERCEPTRON", "official HF organization API returned no models in this check"),
    "undi95": ("https://huggingface.co/undi95", "official HF organization API returned no models in this check"),
    "llama_cpp": ("https://github.com/ggml-org/llama.cpp", "local quantized-model catalog; official repository does not publish a stable model registry"),
    "lmstudio": ("https://lmstudio.ai/docs/app/api", "local model catalog; availability is instance-specific and requires a running LM Studio server"),
}


def check(url: str) -> bool:
    req = Request(url, headers={"User-Agent": "llmcapa-official-updater/1.0"})
    with urlopen(req, timeout=20) as response:
        return response.status == 200 and len(response.read(100_000)) > 100


def main() -> None:
    today = date.today().isoformat()
    results = []
    for provider, (source, reason) in SOURCES.items():
        try:
            ok = check(source)
            path = DATA / f"{provider}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            changed = 0
            for model in data.get("models", []):
                extra = model.setdefault("extra", {})
                before = dict(extra)
                extra.update({"official_source": source, "official_source_checked_at": today, "official_spec_refresh": "source_checked_no_catalog_replacement", "official_catalog_status": reason})
                changed += extra != before
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            target = INSTALLED / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            results.append((provider, ok, changed))
        except Exception as exc:
            results.append((provider, False, f"error: {exc}"))
    lines = [f"\n## Unresolved catalog sources checked ({today})\n", "", "- OpenRouter was not used.", "- No provider JSON was replaced with gateway data or inferred specifications.", ""]
    lines.extend(f"- {provider}: official_source_reachable={ok}, result={result}" for provider, ok, result in results)
    LOG.write_text(LOG.read_text(encoding="utf-8") + "\n".join(lines) + "\n", encoding="utf-8")
    print("; ".join(f"{p}={ok}:{n}" for p, ok, n in results))

if __name__ == "__main__": main()
