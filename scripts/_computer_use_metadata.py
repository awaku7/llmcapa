"""Source-backed Computer Use metadata shared by provider catalog updaters.

Keep provider/platform compatibility separate: a model's ability to perform
computer-use tasks does not imply that every API gateway exposes its tool
protocol.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

ANTHROPIC_COMPUTER_USE_SOURCE = (
    "https://platform.claude.com/docs/en/agents-and-tools/tool-use/computer-use-tool"
)
GOOGLE_COMPUTER_USE_SOURCE = (
    "https://ai.google.dev/gemini-api/docs/generate-content/computer-use"
)
VERTEX_COMPUTER_USE_SOURCE = (
    "https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/computer-use"
)
META_COMPUTER_USE_SOURCE = "https://dev.meta.ai/docs/computer-use"
META_MUSE_SPARK_11_SOURCE = "https://ai.meta.com/blog/introducing-muse-spark-meta-model-api/"
META_COMPUTER_USE_MODELS = frozenset({"muse-spark-1.1", "muse-spark-1.3"})

# These model IDs are explicitly listed in Google's current Computer Use guide.
GOOGLE_COMPUTER_USE_MODELS = frozenset(
    {
        "gemini-3.8-flash",
        "gemini-3.7-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3-flash-preview",
    }
)
GOOGLE_COMPUTER_USE_SHUTDOWNS = {
    "gemini-2.5-computer-use-preview-10-2025": "2026-07-28",
}

# Anthropic's current Computer Use documentation lists these models for the
# computer_toolset_20260801 toolset. Older tool versions have their own exact
# compatibility lists below.
ANTHROPIC_TOOLSET_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-mythos-5-1",
        "claude-fable-5",
        "claude-mythos-5",
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-haiku-5-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
    }
)
ANTHROPIC_COMPUTER_20251124_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-mythos-5-1",
        "claude-fable-5",
        "claude-mythos-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-opus-4-5",
    }
)
ANTHROPIC_COMPUTER_20250124_MODELS = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
        "claude-opus-4-1",
        "claude-sonnet-4",
        "claude-opus-4",
    }
)
AMAZON_COMPUTER_20251124_MODELS = frozenset(
    {
        "claude-opus-5-5",
        "claude-sonnet-5-5",
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-4-6",
        "claude-opus-4-5",
    }
)
AMAZON_COMPUTER_20250124_MODELS = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    }
)
ANTHROPIC_COMPUTER_20250124_CURRENT_MODELS = frozenset(
    {
        "claude-sonnet-4-5",
        "claude-haiku-4-5",
    }
)


def _claude_model_id(model_id: str) -> str:
    """Normalize Anthropic and Bedrock-qualified IDs to Claude's canonical ID."""
    value = str(model_id).strip().lower()
    value = value.removeprefix("anthropic.").replace(".", "-")
    if not value.startswith("claude-"):
        return value
    match = re.match(
        r"^(claude-(?:fable|mythos|opus|sonnet|haiku)-\d+(?:-\d+)?)(?:-|$)",
        value,
    )
    return match.group(1) if match else value


def _computer_use_record(
    *,
    provider: str,
    model_id: str,
    api_type: str,
    tool_type: str,
    tool_version: str,
    status: str,
    source_url: str,
    requires_beta: bool = False,
    beta_header: str | None = None,
    environments: tuple[str, ...] = (),
    enable_zoom: bool = False,
) -> dict:
    return {
        "supported": True,
        "native": True,
        "provider": provider,
        "model": model_id,
        "api_type": api_type,
        "tool_type": tool_type,
        "tool_version": tool_version,
        "status": status,
        "environments": list(environments),
        "requires_beta": requires_beta,
        "enable_zoom": enable_zoom,
        "source_url": source_url,
        "checked_at": datetime.now(timezone.utc).date().isoformat(),
        **({"beta_header": beta_header} if beta_header else {}),
    }


def google_computer_use_capability(
    model_id: str, provider: str = "google"
) -> dict | None:
    """Return documented Gemini Computer Use metadata for a supported model."""
    if model_id not in GOOGLE_COMPUTER_USE_MODELS:
        return None
    source = VERTEX_COMPUTER_USE_SOURCE if provider == "vertex-ai" else GOOGLE_COMPUTER_USE_SOURCE
    return _computer_use_record(
        provider=provider,
        model_id=model_id,
        api_type="generate_content",
        tool_type="computer_use",
        tool_version="",
        status="preview",
        source_url=source,
        environments=("browser", "desktop", "mobile"),
    ) | {"tool_version": None}


def anthropic_computer_use_capability(
    model_id: str, platform: str = "anthropic"
) -> dict | None:
    """Return the documented Claude tool/version for a specific API platform.

    Anthropic API and Google Cloud support the current client toolset. Amazon
    Bedrock and Microsoft Foundry expose the earlier beta tool versions only,
    with Bedrock's documented Opus/Sonnet 5.5 exception.
    """
    canonical = _claude_model_id(model_id)
    platform = platform.lower().replace("_", "-")
    if platform in {"anthropic", "vertex-ai", "google-cloud"}:
        if canonical in ANTHROPIC_TOOLSET_MODELS:
            return _computer_use_record(
                provider=platform,
                model_id=model_id,
                api_type="messages",
                tool_type="computer_toolset_20260801",
                tool_version="20260801",
                status="ga",
                source_url=ANTHROPIC_COMPUTER_USE_SOURCE,
                environments=("desktop",),
                enable_zoom=True,
            )

        if canonical in ANTHROPIC_COMPUTER_20251124_MODELS:
            version = "20251124"
            return _computer_use_record(
                provider=platform,
                model_id=model_id,
                api_type="messages",
                tool_type=f"computer_{version}",
                tool_version=version,
                status="beta",
                source_url=ANTHROPIC_COMPUTER_USE_SOURCE,
                requires_beta=True,
                beta_header="computer-use-2025-11-24",
                environments=("desktop",),
                enable_zoom=True,
            )
        if canonical in ANTHROPIC_COMPUTER_20250124_CURRENT_MODELS or (
            platform in {"vertex-ai", "google-cloud"}
            and canonical in ANTHROPIC_COMPUTER_20250124_MODELS
        ):
            version = "20250124"
            return _computer_use_record(
                provider=platform,
                model_id=model_id,
                api_type="messages",
                tool_type=f"computer_{version}",
                tool_version=version,
                status="beta",
                source_url=ANTHROPIC_COMPUTER_USE_SOURCE,
                requires_beta=True,
                beta_header="computer-use-2025-01-24",
                environments=("desktop",),
            )
        return None

    if platform in {"amazon", "amazon-bedrock"}:
        # Bedrock supports the earlier beta tool versions. Opus/Sonnet 5.5
        # are explicitly documented to accept computer_20251124 there.
        if canonical in AMAZON_COMPUTER_20251124_MODELS:
            version = "20251124"
        elif canonical in AMAZON_COMPUTER_20250124_MODELS:
            version = "20250124"
        else:
            return None
        return _computer_use_record(
            provider="amazon",
            model_id=model_id,
            api_type="bedrock-runtime",
            tool_type=f"computer_{version}",
            tool_version=version,
            status="beta",
            source_url="https://docs.aws.amazon.com/bedrock/latest/userguide/computer-use.html",
            requires_beta=True,
            beta_header=f"computer-use-2025-{version[4:6]}-{version[6:8]}",
            environments=("desktop",),
            enable_zoom=version == "20251124",
        )

    if platform in {"azure-foundry", "microsoft-foundry"}:
        if canonical in ANTHROPIC_COMPUTER_20251124_MODELS:
            version = "20251124"
        elif canonical in ANTHROPIC_COMPUTER_20250124_CURRENT_MODELS:
            version = "20250124"
        else:
            return None
        return _computer_use_record(
            provider="azure-foundry",
            model_id=model_id,
            api_type="messages",
            tool_type=f"computer_{version}",
            tool_version=version,
            status="beta",
            source_url=ANTHROPIC_COMPUTER_USE_SOURCE,
            requires_beta=True,
            beta_header=f"computer-use-2025-{version[4:6]}-{version[6:8]}",
            environments=("desktop",),
            enable_zoom=version == "20251124",
        )
    return None


def meta_computer_use_capability(model_id: str) -> dict | None:
    """Return Meta's documented Muse Spark native Computer Use metadata."""
    if model_id not in META_COMPUTER_USE_MODELS:
        return None
    source = (
        META_MUSE_SPARK_11_SOURCE
        if model_id == "muse-spark-1.1"
        else META_COMPUTER_USE_SOURCE
    )
    return _computer_use_record(
        provider="meta",
        model_id=model_id,
        api_type="responses",
        tool_type="computer",
        tool_version="",
        status="documented",
        source_url=source,
        environments=("browser", "desktop"),
    ) | {"tool_version": None}
