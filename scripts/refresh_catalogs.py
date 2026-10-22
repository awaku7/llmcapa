"""Safely refresh official provider catalogs and report every model-level change.

Each provider updater runs independently. Successful updates are staged and
failures are rolled back without losing earlier successful updates.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from _update_all_providers import PROVIDER_SCRIPTS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "src" / "llmcapa" / "data"
DEFAULT_OUTPUT = ROOT / "outputs" / "catalog_refresh"
CATALOG_FILENAME_OVERRIDES = {
    "azure-foundry": "azure_foundry.json",
    "foundry-local": "foundry_local.json",
    "llama-cpp": "llama_cpp.json",
}
IGNORED_TRACKED_SIDE_EFFECTS = {"provider_update_log.md"}


def catalog_filename(provider: str) -> str:
    return CATALOG_FILENAME_OVERRIDES.get(provider, f"{provider}.json")


def model_index(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Validate a catalog and index models without silently losing duplicates."""
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("catalog has no models")
    result: dict[str, dict[str, Any]] = {}
    for model in models:
        if not isinstance(model, dict):
            raise TypeError("model record is not an object")
        model_id = model.get("model_id")
        if not isinstance(model_id, str) or not model_id.strip():
            raise ValueError("model_id is missing or empty")
        if model_id in result:
            raise ValueError(f"duplicate model_id: {model_id}")
        result[model_id] = model
    return result


def load_catalog(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError("catalog root is not an object")
    model_index(data)
    return data


def _pricing_tier_identity(item: Any) -> tuple[tuple[str, Any], ...]:
    """Identify a published rate tier by its documented applicability."""
    if not isinstance(item, dict):
        return ()
    identifiers = (
        "input_context",
        "min_prompt_tokens",
        "max_prompt_tokens",
        "min_input_tokens",
        "max_input_tokens",
        "region",
        "region_id",
        "tier",
    )
    return tuple((key, item[key]) for key in identifiers if item.get(key) is not None)


def _protect_known_pricing(
    previous: Any, current: Any, model_id: str, path: str
) -> None:
    """Reject lost known prices inside nested dictionaries and tier lists."""
    if previous is None:
        return
    if current is None:
        raise ValueError(f"{model_id}: known {path} was lost")
    if isinstance(previous, dict):
        if not isinstance(current, dict):
            raise TypeError(f"{model_id}: invalid {path} pricing container")
        for key, value in previous.items():
            _protect_known_pricing(value, current.get(key), model_id, f"{path}.{key}")
    elif isinstance(previous, list):
        if not isinstance(current, list) or len(current) < len(previous):
            raise ValueError(f"{model_id}: known {path} was lost")
        used_indices: set[int] = set()
        for index, value in enumerate(previous):
            identity = _pricing_tier_identity(value)
            if identity:
                matches = [
                    position
                    for position, candidate in enumerate(current)
                    if position not in used_indices
                    and isinstance(candidate, dict)
                    and all(
                        candidate.get(key) == expected for key, expected in identity
                    )
                ]
                if not matches:
                    raise ValueError(f"{model_id}: known {path}[{index}] tier was lost")
                matched_index = matches[0]
            else:
                matched_index = index
                if matched_index in used_indices:
                    raise ValueError(f"{model_id}: known {path}[{index}] was lost")
            used_indices.add(matched_index)
            _protect_known_pricing(
                value, current[matched_index], model_id, f"{path}[{index}]"
            )


def validate_refreshed_catalog(
    previous: dict[str, Any], updated: dict[str, Any]
) -> None:
    """Reject incomplete records or loss of previously documented capabilities.

    Official pages often omit previously published fields; omission is not
    evidence that a capability or a known price has been withdrawn. In those
    cases, preserve the entire previous catalog until the updater is fixed.
    """
    old = model_index(previous)
    new = model_index(updated)
    for model_id, row in new.items():
        for key in ("context_window", "max_output_tokens"):
            value = row.get(key)
            if type(value) is not int or value < 0:
                raise ValueError(f"{model_id}: missing or invalid {key}")

    for model_id, previous_row in old.items():
        refreshed = new.get(model_id)
        if refreshed is None:
            # An omitted row is not evidence of retirement. Preserve the
            # existing catalog until an explicit, reviewed removal is made.
            raise ValueError(f"{model_id}: model disappeared from provider catalog")

        for key in (
            "image",
            "audio",
            "video",
            "decision",
            "document",
            "embedding",
            "rerank",
            "computer_use",
            "spatial",
        ):
            if previous_row.get(key) and not refreshed.get(key):
                raise ValueError(f"{model_id}: documented {key} was lost")
        for key in ("context_window", "max_output_tokens"):
            if previous_row.get(key, 0) > 0 and refreshed[key] == 0:
                raise ValueError(f"{model_id}: known {key} became zero")

        for key in ("input_modalities", "output_modalities"):
            documented = previous_row.get(key)
            if not isinstance(documented, list) or not documented:
                continue
            current = refreshed.get(key)
            if not isinstance(current, list) or any(
                modality not in current for modality in documented
            ):
                raise ValueError(f"{model_id}: documented {key} was lost")

        previous_pricing = previous_row.get("pricing") or {}
        refreshed_pricing = refreshed.get("pricing") or {}
        if not isinstance(refreshed_pricing, dict):
            raise TypeError(f"{model_id}: invalid pricing")
        # Protect all nested token-pricing details, including known zeroes.
        for key, known_value in previous_pricing.items():
            _protect_known_pricing(
                known_value, refreshed_pricing.get(key), model_id, key
            )

        previous_extra = previous_row.get("extra")
        refreshed_extra = refreshed.get("extra")
        if previous_extra is not None and not isinstance(previous_extra, dict):
            raise TypeError(f"{model_id}: invalid previous extra")
        if refreshed_extra is not None and not isinstance(refreshed_extra, dict):
            raise TypeError(f"{model_id}: invalid extra")
        previous_extra = previous_extra or {}
        refreshed_extra = refreshed_extra or {}
        # Non-token prices are usually kept in extra. Do not enumerate only
        # today's Mistral keys: images, speech, video, and new APIs may
        # introduce other published units. Preserve 0.0 as a known rate.
        for key, known_value in previous_extra.items():
            is_billing_field = "_per_" in key.casefold() or any(
                word in key.casefold()
                for word in ("price", "pricing", "cost", "rate", "billing")
            )
            if is_billing_field:
                _protect_known_pricing(
                    known_value, refreshed_extra.get(key), model_id, key
                )

        previous_cached = previous_extra.get("cached_input_per_1m")
        previous_output = previous_pricing.get("output_per_1m")
        refreshed_cached = refreshed_extra.get("cached_input_per_1m")
        if (
            previous_cached is not None
            and previous_output is not None
            and previous_cached != previous_output
            and refreshed_pricing.get("output_per_1m") == previous_cached
            and refreshed_cached == previous_output
        ):
            raise ValueError(f"{model_id}: cached and output prices swapped")


def changed_fields(before: Any, after: Any, prefix: str = "") -> list[str]:
    """Report nested object changes without expanding individual list elements."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        paths: list[str] = []
        for key in sorted(before.keys() | after.keys()):
            path = f"{prefix}.{key}" if prefix else str(key)
            if key not in before or key not in after:
                paths.append(path)
            else:
                paths.extend(changed_fields(before[key], after[key], path))
        return paths
    return [prefix] if prefix else ["(value)"]


def compare_catalogs(
    previous: dict[str, Any], updated: dict[str, Any]
) -> dict[str, Any]:
    old = model_index(previous)
    new = model_index(updated)
    added = sorted(new.keys() - old.keys())
    removed = sorted(old.keys() - new.keys())
    modified: dict[str, list[str]] = {}
    for model_id in sorted(old.keys() & new.keys()):
        fields = changed_fields(old[model_id], new[model_id])
        if fields:
            modified[model_id] = fields

    # An upstream HTTP error or parser regression must not empty a catalog.
    if len(removed) > max(1, len(old) // 5):
        raise ValueError(
            f"suspicious deletion: {len(removed)} of {len(old)} old models"
        )
    return {"added": added, "removed": removed, "modified": modified}


def unstaged_files() -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "-z", "--"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return {name for name in result.stdout.decode("utf-8").split("\0") if name}


def restore_unstaged() -> None:
    # The index contains all earlier successful providers. Restore from the
    # index, not HEAD, so a later failed updater cannot erase their changes.
    subprocess.run(["git", "restore", "--worktree", "--", "."], cwd=ROOT, check=True)


def run_provider(
    provider: str, *, timeout_seconds: int, log_directory: Path
) -> dict[str, Any]:
    filename = catalog_filename(provider)
    path = DATA_DIR / filename
    relative_path = path.relative_to(ROOT).as_posix()
    status: dict[str, Any] = {"provider": provider, "status": "failed"}
    if not path.is_file():
        status["reason"] = f"catalog file missing: {filename}"
        return status

    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"{provider}.log"
    try:
        previous = load_catalog(path)
        with log_path.open("w", encoding="utf-8") as log:
            command = [
                sys.executable,
                str(ROOT / "scripts" / "_update_all_providers.py"),
                "--provider",
                provider,
            ]
            proc = subprocess.Popen(
                command,
                cwd=ROOT,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=os.name != "nt",
                creationflags=(
                    subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
                ),
            )
            try:
                returncode = proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                # Stop the whole group, including provider-update descendants,
                # before the finally block restores tracked files.
                if os.name != "nt":
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    # Windows has no os.killpg; taskkill /T includes descendants.
                    subprocess.run(
                        ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    )
                proc.wait()
                raise
        if returncode:
            raise RuntimeError(f"updater exited with code {returncode}")

        touched = unstaged_files()
        unexpected = touched - {relative_path} - IGNORED_TRACKED_SIDE_EFFECTS
        if unexpected:
            raise ValueError(f"unexpected files modified: {sorted(unexpected)}")

        updated = load_catalog(path)
        validate_refreshed_catalog(previous, updated)
        diff = compare_catalogs(previous, updated)
        if relative_path in touched and any(diff.values()):
            subprocess.run(["git", "add", "--", relative_path], cwd=ROOT, check=True)
        status["status"] = "updated" if any(diff.values()) else "unchanged"
        status["changes"] = diff
    except subprocess.TimeoutExpired:
        status["reason"] = f"updater timed out after {timeout_seconds}s"
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        status["reason"] = str(exc)[:300]
    finally:
        restore_unstaged()
    return status


def _safe_markdown(value: str) -> str:
    return value.replace("\r", " ").replace("\n", " ").replace("`", "'")


def write_reports(
    results: list[dict[str, Any]], output_directory: Path
) -> dict[str, int]:
    output_directory.mkdir(parents=True, exist_ok=True)
    counts = {
        "updated": sum(r["status"] == "updated" for r in results),
        "unchanged": sum(r["status"] == "unchanged" for r in results),
        "failed": sum(r["status"] == "failed" for r in results),
        "unsupported": sum(r["status"] == "unsupported" for r in results),
    }
    added = sum(len(r.get("changes", {}).get("added", [])) for r in results)
    modified = sum(len(r.get("changes", {}).get("modified", {})) for r in results)
    removed = sum(len(r.get("changes", {}).get("removed", [])) for r in results)
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "providers": results,
        "totals": {**counts, "added": added, "modified": modified, "removed": removed},
    }
    (output_directory / "report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# llmcapa catalog refresh report",
        "",
        f"- Updated providers: {counts['updated']}",
        f"- Unchanged providers: {counts['unchanged']}",
        f"- Failed providers: {counts['failed']}",
        f"- Without updater: {counts['unsupported']}",
        f"- Added models: {added}",
        f"- Modified models: {modified}",
        f"- Removed models: {removed}",
        "",
        "The report covers official, provider-specific updaters only. Failed",
        "updaters retain their existing catalog data. Full model changes appear below.",
        "",
    ]
    for result in results:
        provider = result["provider"]
        state = result["status"]
        lines.extend([f"## {_safe_markdown(provider)} — {state}", ""])
        if "reason" in result:
            lines.extend([f"Reason: {_safe_markdown(result['reason'])}", ""])
        changes = result.get("changes", {})
        for model_id in changes.get("added", []):
            lines.append(f"- Added: `{_safe_markdown(model_id)}`")
        for model_id, fields in changes.get("modified", {}).items():
            formatted = ", ".join(f"`{_safe_markdown(field)}`" for field in fields)
            lines.append(f"- Modified: `{_safe_markdown(model_id)}` ({formatted})")
        for model_id in changes.get("removed", []):
            lines.append(f"- Removed: `{_safe_markdown(model_id)}`")
        lines.append("")
    (output_directory / "report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return summary["totals"]


def refresh(
    selected_provider: str, timeout_seconds: int, output_directory: Path
) -> dict[str, int]:
    # A rollback restores the working tree from the Git index. Never do that
    # when a developer already has uncommitted or staged changes.
    for args in (
        ["git", "diff", "--quiet", "--"],
        ["git", "diff", "--cached", "--quiet", "--"],
    ):
        if subprocess.run(args, cwd=ROOT, check=False).returncode:
            raise ValueError("catalog refresh requires a clean Git working tree")

    if selected_provider != "all" and selected_provider not in PROVIDER_SCRIPTS:
        raise ValueError(f"unknown provider: {selected_provider}")

    providers = (
        sorted(PROVIDER_SCRIPTS) if selected_provider == "all" else [selected_provider]
    )
    statuses = []
    for index, provider in enumerate(providers, 1):
        print(f"[{index}/{len(providers)}] {provider}", flush=True)
        result = run_provider(
            provider,
            timeout_seconds=timeout_seconds,
            log_directory=output_directory / "logs",
        )
        statuses.append(result)
        print(f"  -> {result['status']}: {result.get('reason', '')}", flush=True)

    if selected_provider == "all":
        handled = {catalog_filename(provider) for provider in PROVIDER_SCRIPTS}
        for path in sorted(DATA_DIR.glob("*.json")):
            if path.name not in handled:
                statuses.append(
                    {
                        "provider": path.stem,
                        "status": "unsupported",
                        "reason": "no provider-specific updater",
                    }
                )

    totals = write_reports(statuses, output_directory)
    print(json.dumps(totals, ensure_ascii=False), flush=True)
    return totals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="all")
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.timeout_seconds < 1:
        parser.error("--timeout-seconds must be positive")
    try:
        totals = refresh(args.provider, args.timeout_seconds, args.output)
    except ValueError as exc:
        parser.error(str(exc))
    # Partial failure is shown explicitly in the report and PR.
    return 1 if not totals["updated"] and not totals["unchanged"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
