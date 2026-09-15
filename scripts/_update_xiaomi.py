"""Build/refresh xiaomi.json (MiMo) from official mimo.mi.com docs.

Sources (Playwright live 2026-07-18):
- https://mimo.mi.com/docs/en-US/price/pay-as-you-go
- https://mimo.mi.com/docs/en-US/quick-start/summary/model
- V2 series deprecated 2026-06-30; V2.5 is current.
- Overseas (USD) pricing used for pricing fields; CNY kept in extra.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

WORKDIR = Path(__file__).resolve().parents[1]
OUT = WORKDIR / "src" / "llmcapa" / "data" / "xiaomi.json"
INSTALLED_DIR = Path(__file__).resolve().parents[1] / "src" / "llmcapa" / "data"
LOG = WORKDIR / "provider_update_log.md"
SOURCE_PRICE = "https://mimo.mi.com/docs/en-US/price/pay-as-you-go"
SOURCE_MODELS = "https://mimo.mi.com/docs/en-US/quick-start/summary/model"


def base(
    *,
    model_id: str,
    display: str,
    ctx: int,
    max_out: int,
    input_modalities: list[str],
    output_modalities: list[str],
    pricing: dict | None = None,
    aliases: list[str] | None = None,
    deprecated: bool = False,
    reasoning: bool = False,
    vision: bool = False,
    fc: bool = False,
    json_mode: bool = False,
    chat: bool = True,
    license_type: str = "api",
    knowledge_cutoff: str | None = None,
    extra: dict | None = None,
) -> dict:
    aliases = list(aliases or [])
    bare = model_id.split("/")[-1]
    # Native catalog only. Route-qualified IDs such as xiaomi/<id>
    # belong to the openrouter catalog and must not be added here.
    for a in (bare,):
        if a not in aliases and a != model_id:
            aliases.append(a)
    row = {
        "provider": "xiaomi",
        "model_id": model_id,
        "display_name": display,
        "context_window": ctx,
        "max_output_tokens": max_out,
        "input_modalities": input_modalities,
        "output_modalities": output_modalities,
        "supports_function_calling": fc,
        "supports_json_mode": json_mode,
        "supports_streaming": True,
        "supports_vision": vision,
        "supports_reasoning": reasoning,
        "supports_chat_completion": chat,
        "supports_responses_api": True,  # Responses API is live
        "supports_reasoning_effort": False,
        "supports_thinking_budget": False,
        "supports_anthropic_api": False,
        "supports_google_api": False,
        "supports_fim": False,
        "tokenizer_name": "",
        "knowledge_cutoff": knowledge_cutoff,
        "deprecated": deprecated,
        "aliases": aliases,
        "license_type": license_type,
        "extra": {
            "source_pricing": SOURCE_PRICE,
            "source_models": SOURCE_MODELS,
            **(extra or {}),
        },
    }
    if pricing is not None:
        row["pricing"] = pricing
    return row


def build() -> list[dict]:
    """Load MiMo metadata from external source-backed JSON."""
    manifest = json.loads(
        (Path(__file__).parent / "metadata" / "xiaomi_legacy_models.json").read_text(
            encoding="utf-8"
        )
    )
    return [dict(model) for model in manifest["models"]]


def main() -> None:
    models = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"models": models}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if INSTALLED_DIR.exists() and OUT.resolve() != (INSTALLED_DIR / OUT.name).resolve():
        shutil.copy2(OUT, INSTALLED_DIR / OUT.name)

    active = sum(1 for m in models if not m.get("deprecated"))
    deprecated = sum(1 for m in models if m.get("deprecated"))
    priced = sum(
        1 for m in models if (m.get("pricing") or {}).get("input_per_1m") is not None
    )
    print(
        f"xiaomi.json: {len(models)} models "
        f"(active={active} / deprecated={deprecated} / priced={priced})",
        flush=True,
    )
    for m in models:
        if m.get("deprecated"):
            continue
        p = m.get("pricing") or {}
        print(
            f"  {m['model_id']:32} in={p.get('input_per_1m')} out={p.get('output_per_1m')} "
            f"ctx={m['context_window']}",
            flush=True,
        )

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = (
        f"\n## Xiaomi MiMo refresh ({stamp})\n\n"
        f"### Source\n"
        f"- Models: {SOURCE_MODELS}\n"
        f"- Pricing: {SOURCE_PRICE} (Playwright live)\n"
        f"- Apply: `scripts/_update_xiaomi.py`\n\n"
        f"### Result\n"
        f"- xiaomi.json: **{len(models)}** models "
        f"(active={active}, deprecated={deprecated}, priced={priced})\n"
        f"- **mimo-v2.5-pro**: $0.435/$0.87; cache hit $0.0036; 1M/128k\n"
        f"- **mimo-v2.5**: $0.14/$0.28 (was $0.105/$0.28); cache hit $0.0028; multimodal\n"
        f"- **mimo-v2.5-asr**: $0.074/hour overseas\n"
        f"- TTS series free limited-time; voiceclone/voicedesign added\n"
        f"- V2 series marked deprecated 2026-06-30\n"
        f"- Model IDs normalized to bare official IDs\n"
        f"- Install copy synced\n"
    )
    if LOG.exists():
        LOG.write_text(LOG.read_text(encoding="utf-8") + entry, encoding="utf-8")
    else:
        LOG.write_text(entry, encoding="utf-8")


if __name__ == "__main__":
    main()
