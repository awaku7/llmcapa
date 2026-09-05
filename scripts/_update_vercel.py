"""Normalize Vercel gateway thinking metadata from native catalogs.

Vercel is a gateway, so values are copied by underlying model identity rather
than assigned uniformly to the gateway.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "src" / "llmcapa" / "data" / "vercel.json"
ANTHROPIC = ROOT / "src" / "llmcapa" / "data" / "anthropic.json"
NVIDIA = ROOT / "src" / "llmcapa" / "data" / "nvidia.json"
OPENAI = ROOT / "src" / "llmcapa" / "data" / "openai.json"


def main() -> None:
    data = json.loads(DATA.read_text(encoding="utf-8"))
    anthropic = json.loads(ANTHROPIC.read_text(encoding="utf-8"))["models"]
    nvidia = json.loads(NVIDIA.read_text(encoding="utf-8"))["models"]
    openai = json.loads(OPENAI.read_text(encoding="utf-8"))["models"]
    anthropic_by_id = {m.get("model_id", ""): m for m in anthropic}
    nvidia_by_id = {m.get("model_id", ""): m for m in nvidia}
    openai_by_id = {m.get("model_id", ""): m for m in openai}
    updated = 0

    for model in data.get("models", []):
        model_id = str(model.get("model_id", ""))
        bare_id = model_id.split("/", 1)[-1]
        control = None

        # Vercel exposes native OpenAI models through a gateway. Mirror the
        # native reasoning_effort metadata instead of leaving the gateway's
        # default flag at False.
        native_openai = openai_by_id.get(bare_id)
        if native_openai:
            values = native_openai.get("reasoning_effort_values")
            if native_openai.get("supports_reasoning_effort") is True:
                model["supports_reasoning_effort"] = True
            if values:
                model["supports_reasoning_effort"] = True
                model["reasoning_effort_values"] = list(values)

        if bare_id in anthropic_by_id:
            native = anthropic_by_id[bare_id]
            values = native.get("thinking_budget_values")
            if values:
                model["supports_thinking_budget"] = True
                model["thinking_budget_values"] = dict(values)
                control = {
                    "kind": "budget",
                    "parameter": "thinking_budget",
                    **values,
                    "native_provider": "anthropic",
                }
        elif bare_id in nvidia_by_id:
            native = nvidia_by_id[bare_id]
            values = native.get("thinking_budget_values")
            if values:
                model["supports_thinking_budget"] = True
                model["thinking_budget_values"] = dict(values)
                control = {
                    "kind": "budget",
                    "parameter": "thinking_budget",
                    **values,
                    "native_provider": "nvidia",
                }
        elif bare_id == "MiniMax-M3":
            model["supports_thinking_budget"] = False
            model["thinking_control"] = {
                "kind": "toggle",
                "parameter": "thinking",
                "values": ["enabled", "disabled"],
                "native_provider": "minimax",
            }
            control = model["thinking_control"]

        if control:
            model["thinking_control"] = control
            model.setdefault("extra", {})["native_model_id"] = bare_id
            updated += 1

    DATA.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"vercel.json: {updated} gateway records normalized from native catalogs")


if __name__ == "__main__":
    main()
