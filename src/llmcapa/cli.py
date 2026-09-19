"""Command line interface for llmcapa.

Usage:
    llmcapa show <model_id> [--json]
    llmcapa list [OPTIONS]
    llmcapa search <prefix> [OPTIONS]
    llmcapa find [NAME[=BOOL] ...] [OPTIONS]
    llmcapa providers
    llmcapa tokens <model_id> [TEXT] [--messages]
    llmcapa update
    llmcapa fetch-hf [--limit N]

Rendering options shared by ``list`` and ``search``:

    --format {table,json,csv,md}  output format (default: table)
    --json                        shortcut for ``--format json``
    --columns a,b,c               select and order columns
    --sort KEY[,KEY]              sort keys; prefix a key with "-" for descending
    --limit N                     maximum number of rows, applied after sorting
    --all                         include deprecated models (hidden by default)
    --wide                        add extra columns and disable clipping
    --width N                     table width budget (default: terminal, 120 piped)
    --allow-empty                 exit 0 even when nothing matched

Deprecated models are hidden unless ``--all`` is given, and when shown they are
always ordered after the active ones.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from typing import Any, Callable, Sequence

from . import (
    __version__,
    count_messages_tokens,
    count_tokens,
    find,
    get,
    list_models,
    providers,
    search,
)
from .models import Capability
from .registry import ModelNotFoundError, default_registry

# ---------------------------------------------------------------------------
# cell formatters
# ---------------------------------------------------------------------------


def _fmt_tokens(value: int | None) -> str:
    """Format a token count as ``-`` / ``1234`` / ``65.5K`` / ``1M``.

    Zero and ``None`` mean "not verified in the catalog" and render as ``-``
    so that an unknown limit is never confused with a limit of zero.
    """
    if not value:
        return "-"
    if value >= 1_000_000:
        scaled, unit = value / 1_000_000, "M"
    elif value >= 1_000:
        scaled, unit = value / 1_000, "K"
    else:
        return str(value)
    if scaled >= 100:
        return f"{scaled:.0f}{unit}"
    return f"{scaled:.1f}".rstrip("0").rstrip(".") + unit


def _fmt_rate(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


_CURRENCY_SYMBOLS = {"USD": "$"}


def _fmt_price(cap: Capability) -> str:
    """Format ``input_per_1m``/``output_per_1m`` as e.g. ``$2.5/15``."""
    pricing = cap.pricing
    if not isinstance(pricing, dict):
        return "-"
    inp = pricing.get("input_per_1m")
    out = pricing.get("output_per_1m")
    if inp is None and out is None:
        return "-"
    currency = str(pricing.get("currency") or "USD")
    prefix = _CURRENCY_SYMBOLS.get(currency, f"{currency} ")
    return f"{prefix}{_fmt_rate(inp)}/{_fmt_rate(out)}"


def _tri(value: bool | None) -> str:
    """Render a tri-state flag: ``yes`` / ``no`` / ``?`` (unknown)."""
    if value is None:
        return "?"
    return "yes" if value else "no"


def _flags(cap: Capability) -> str:
    """Five-slot feature column: vision, tools, reasoning, json, streaming."""
    slots = (
        cap.supports_vision,
        cap.supports_function_calling,
        cap.supports_reasoning,
        cap.supports_json_mode,
        cap.supports_streaming,
    )
    return "".join(
        "-" if v is False else ("?" if v is None else ch)
        for ch, v in zip("VTRJS", slots)
    )


# Specialized (nested) capability records that can be queried per row.
_CAPABILITY_NAMES: tuple[str, ...] = (
    "image",
    "audio",
    "video",
    "document",
    "embedding",
    "rerank",
    "spatial",
    "decision",
)


def _cap_flag(cap: Capability, name: str) -> str:
    """Report the specialized *name* capability record for a model.

    A nested record whose primary field is absent (``image``, ``audio`` and
    ``video`` are per-operation records) counts as supported when it exists.
    Without a record, an output modality counts as supported while an
    input-only modality stays unknown, because accepting images as input says
    nothing about image generation.
    """
    obj = getattr(cap, name, None)
    if obj is not None:
        if hasattr(obj, name):
            return _tri(getattr(obj, name))
        return "yes"
    if name in cap.output_modalities:
        return "yes"
    return "?" if name in cap.input_modalities else "-"


def _decision_field(cap: Capability, attr: str) -> str:
    """Return one ``cap.decision`` field, joined when it is a sequence."""
    record = cap.decision
    if record is None:
        return "-"
    value = getattr(record, attr, None)
    if value is None or value == () or value == "":
        return "-"
    if isinstance(value, (tuple, list)):
        return ",".join(str(v) for v in value)
    return str(value)


def _decision_pck(cap: Capability) -> str:
    """Three slots: returns probabilities, confidence, calibrated confidence."""
    record = cap.decision
    if record is None:
        return "-"
    slots = (
        record.returns_probabilities,
        record.returns_confidence,
        record.calibrated_confidence,
    )
    if all(v is None for v in slots):
        return "-"
    return "".join(
        "-" if v is False else ("?" if v is None else ch)
        for ch, v in zip("PCK", slots)
    )


def _decision_state(cap: Capability) -> str:
    """Format ``max_state_tokens``/``max_total_tokens``."""
    record = cap.decision
    if record is None:
        return "-"
    state, total = record.max_state_tokens, record.max_total_tokens
    if not state and not total:
        return "-"
    return f"{_fmt_tokens(state)}/{_fmt_tokens(total)}"


# ---------------------------------------------------------------------------
# columns
# ---------------------------------------------------------------------------

_COLUMN_ALIASES: dict[str, str] = {
    "depmark": "depmark",
    "dep": "depmark",
    "star": "depmark",
    "mark": "depmark",
    "deprecated": "deprecated",
    "is_deprecated": "deprecated",
    "provider": "provider",
    "model_id": "model_id",
    "model": "model_id",
    "id": "model_id",
    "display_name": "name",
    "name": "name",
    "ctx": "ctx",
    "context": "ctx",
    "context_window": "ctx",
    "out": "out",
    "max_out": "out",
    "max_output_tokens": "out",
    "flags": "flags",
    "features": "flags",
    "vision": "vision",
    "tools": "tools",
    "function_calling": "tools",
    "reasoning": "reasoning",
    "json": "json",
    "json_mode": "json",
    "streaming": "streaming",
    "in_mod": "in_mod",
    "input_modalities": "in_mod",
    "out_mod": "out_mod",
    "output_modalities": "out_mod",
    "price": "price",
    "pricing": "price",
    "cutoff": "cutoff",
    "knowledge_cutoff": "cutoff",
    "license": "license",
    "tokenizer": "tokenizer",
    "aliases": "aliases",
    # specialized capability records
    "decision": "decision",
    "dec": "decision",
    "image": "image",
    "audio": "audio",
    "video": "video",
    "document": "document",
    "doc": "document",
    "embedding": "embedding",
    "embed": "embedding",
    "rerank": "rerank",
    "rank": "rerank",
    "spatial": "spatial",
    "q_kinds": "q_kinds",
    "question_kinds": "q_kinds",
    "kinds": "q_kinds",
    "answers": "answers",
    "answer_fields": "answers",
    "pck": "pck",
    "prob": "pck",
    "probabilities": "pck",
    "state": "state",
    "state_tokens": "state",
}

_COLUMNS: dict[str, tuple[str, Callable[[Capability], str]]] = {
    "depmark": ("*", lambda c: "*" if c.deprecated else ""),
    "deprecated": ("deprecated", lambda c: "yes" if c.deprecated else "no"),
    "provider": ("provider", lambda c: c.provider),
    "model_id": ("model_id", lambda c: c.model_id),
    "name": ("display_name", lambda c: c.display_name or "-"),
    "ctx": ("ctx", lambda c: _fmt_tokens(c.context_window)),
    "out": ("out", lambda c: _fmt_tokens(c.max_output_tokens)),
    "flags": ("VTRJS", _flags),
    "vision": ("vision", lambda c: _tri(c.supports_vision)),
    "tools": ("tools", lambda c: _tri(c.supports_function_calling)),
    "reasoning": ("reasoning", lambda c: _tri(c.supports_reasoning)),
    "json": ("json", lambda c: _tri(c.supports_json_mode)),
    "streaming": ("streaming", lambda c: _tri(c.supports_streaming)),
    "in_mod": ("in_mod", lambda c: ",".join(c.input_modalities) or "-"),
    "out_mod": ("out_mod", lambda c: ",".join(c.output_modalities) or "-"),
    "price": ("$/1M in/out", _fmt_price),
    "cutoff": ("cutoff", lambda c: c.knowledge_cutoff or "-"),
    "license": ("license", lambda c: c.license_type or "-"),
    "tokenizer": ("tokenizer", lambda c: c.tokenizer_name or "-"),
    "aliases": ("aliases", lambda c: ",".join(c.aliases) or "-"),
    # specialized capability records
    "decision": ("decision", lambda c: _cap_flag(c, "decision")),
    "image": ("image", lambda c: _cap_flag(c, "image")),
    "audio": ("audio", lambda c: _cap_flag(c, "audio")),
    "video": ("video", lambda c: _cap_flag(c, "video")),
    "document": ("document", lambda c: _cap_flag(c, "document")),
    "embedding": ("embedding", lambda c: _cap_flag(c, "embedding")),
    "rerank": ("rerank", lambda c: _cap_flag(c, "rerank")),
    "spatial": ("spatial", lambda c: _cap_flag(c, "spatial")),
    "q_kinds": ("q_kinds", lambda c: _decision_field(c, "question_kinds")),
    "answers": ("answers", lambda c: _decision_field(c, "answer_fields")),
    "pck": ("PCK", _decision_pck),
    "state": ("state", _decision_state),
}

_DEFAULT_COLUMNS: tuple[str, ...] = (
    "depmark",
    "provider",
    "model_id",
    "ctx",
    "out",
    "flags",
    "price",
)
_WIDE_COLUMNS: tuple[str, ...] = (
    "name",
    "in_mod",
    "out_mod",
    "cutoff",
    "decision",
    "image",
    "audio",
    "video",
)


def _resolve_columns(
    spec: str | None, wide: bool, machine: bool = False
) -> list[tuple[str, Callable[[Capability], str]]]:
    """Return the (header, extractor) pairs for the requested columns.

    With ``machine=True`` (csv/markdown) the wildcard-only deprecated marker is
    replaced by an explicit ``deprecated yes/no`` column.
    """
    names: list[str] = []
    if spec:
        for raw in spec.split(","):
            token = raw.strip().lower()
            if not token:
                continue
            canonical = _COLUMN_ALIASES.get(token)
            if canonical is None:
                raise ValueError(token)
            if canonical not in names:
                names.append(canonical)
    else:
        names = list(_DEFAULT_COLUMNS)
        if wide:
            names.extend(_WIDE_COLUMNS)
    if machine:
        names = ["deprecated" if n == "depmark" else n for n in names]
    return [_COLUMNS[n] for n in names]


# ---------------------------------------------------------------------------
# sorting
# ---------------------------------------------------------------------------

_SORT_KEYS: tuple[str, ...] = (
    "provider",
    "model_id",
    "name",
    "ctx",
    "out",
    "input",
    "output",
    "cutoff",
    "vision",
    "tools",
    "reasoning",
    "json",
    "streaming",
    "deprecated",
) + _CAPABILITY_NAMES

_FLAG_SORT = {
    "vision": "supports_vision",
    "tools": "supports_function_calling",
    "reasoning": "supports_reasoning",
    "json": "supports_json_mode",
    "streaming": "supports_streaming",
}


def _sort_value(cap: Capability, key: str) -> object:
    if key == "provider":
        return cap.provider.lower()
    if key == "model_id":
        return cap.model_id.lower()
    if key == "name":
        return (cap.display_name or cap.model_id).lower()
    if key == "ctx":
        return cap.context_window or -1
    if key == "out":
        return cap.max_output_tokens or -1
    if key == "cutoff":
        return cap.knowledge_cutoff or ""
    if key == "deprecated":
        return cap.deprecated
    if key in ("input", "output"):
        pricing = cap.pricing if isinstance(cap.pricing, dict) else {}
        rate = pricing.get(f"{key}_per_1m")
        return float(rate) if isinstance(rate, (int, float)) else -1.0
    if key in _FLAG_SORT:
        value = getattr(cap, _FLAG_SORT[key])
        return 0 if value is None else (1 if value else 0)
    if key in _CAPABILITY_NAMES:
        flag = _cap_flag(cap, key)
        return {"yes": 1, "-": 0}.get(flag, -1)
    raise KeyError(key)


def _parse_sort(spec: str | None) -> list[tuple[str, bool]]:
    if not spec:
        return [("provider", False), ("model_id", False)]
    keys: list[tuple[str, bool]] = []
    for raw in spec.split(","):
        token = raw.strip()
        if not token:
            continue
        descending = token.startswith("-")
        if not descending and token.startswith("+"):
            token = token[1:]
        name = (token[1:] if descending else token).strip().lower()
        if ":" in name:
            name, _, direction = name.partition(":")
            direction = direction.strip().lower()
            if direction in ("desc", "descending"):
                descending = True
            elif direction in ("asc", "ascending"):
                descending = False
            else:
                raise ValueError(direction)
        if name not in _SORT_KEYS:
            raise ValueError(name)
        keys.append((name, descending))
    return keys or [("provider", False), ("model_id", False)]


def _sort_caps(caps: list[Capability], spec: str | None) -> list[Capability]:
    """Sort with active models first, then the requested keys (stable)."""
    keys = _parse_sort(spec)
    order: list[tuple[str, bool]] = [("deprecated", False)] + keys
    if not any(name == "model_id" for name, _ in keys):
        order.append(("model_id", False))
    for name, descending in reversed(order):
        caps.sort(key=lambda c, n=name: _sort_value(c, n), reverse=descending)
    return caps


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _table_width(args: argparse.Namespace) -> int | None:
    if args.wide:
        return None
    if getattr(args, "width", None):
        return int(args.width)
    if sys.stdout.isatty():
        return shutil.get_terminal_size((120, 24)).columns
    return 120


def _render_table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    max_width: int | None,
    shrink: int = 0,
) -> list[str]:
    ncols = len(headers)
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    if max_width and ncols:
        def total(budget: list[int]) -> int:
            return sum(budget) + 2 * (ncols - 1)

        for i in [shrink] + [j for j in range(ncols) if j != shrink]:
            if total(widths) <= max_width:
                break
            minimum = max(len(headers[i]), 8)
            overflow = total(widths) - max_width
            widths[i] = max(minimum, widths[i] - overflow)

    fmt = "  ".join("{:<%d}" % w for w in widths)
    lines = [
        fmt.format(*[_clip(h, widths[i]) for i, h in enumerate(headers)]).rstrip(),
        fmt.format(*["-" * w for w in widths]).rstrip(),
    ]
    for row in rows:
        lines.append(
            fmt.format(*[_clip(cell, widths[i]) for i, cell in enumerate(row)]).rstrip()
        )
    return lines


def _emit(caps: list[Capability], args: argparse.Namespace) -> int:
    """Render *caps* according to the format/column/sort options in *args*."""
    fmt = "json" if getattr(args, "json", False) else (args.format or "table")
    if fmt == "markdown":
        fmt = "md"

    if fmt == "json":
        print(json.dumps([c.to_dict() for c in caps], ensure_ascii=False, indent=2))
        return 0

    columns = _resolve_columns(
        getattr(args, "columns", None),
        getattr(args, "wide", False),
        machine=fmt in ("csv", "md"),
    )
    headers = [h for h, _ in columns]
    rows = [[extract(c) for _, extract in columns] for c in caps]

    if fmt == "csv":
        writer = csv.writer(sys.stdout, lineterminator="\n")
        writer.writerow(headers)
        writer.writerows(rows)
        return 0

    if fmt == "md":
        def escape(cell: str) -> str:
            return cell.replace("|", "\\|")

        print("| " + " | ".join(escape(h) for h in headers) + " |")
        print("| " + " | ".join("---" for _ in headers) + " |")
        for row in rows:
            print("| " + " | ".join(escape(cell) for cell in row) + " |")
        return 0

    if caps:
        model_col = headers.index("model_id") if "model_id" in headers else 0
        for line in _render_table(headers, rows, _table_width(args), model_col):
            print(line)
        if sys.stdout.isatty():
            note = f"({len(caps)} models"
            if "*" in headers and any(c.deprecated for c in caps):
                note += "; * = deprecated"
            print(note + ")", file=sys.stderr)
    return 0


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


def _format_show_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) if value else "(empty)"
    if value is None:
        return "(none)"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def _iter_show_rows(
    data: dict[str, Any], prefix: str = ""
) -> list[tuple[str, str]]:
    """Flatten nested capability dicts into dotted ``key  value`` rows."""
    rows: list[tuple[str, str]] = []
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            rows.extend(_iter_show_rows(value, prefix=f"{name}."))
            continue
        rows.append((name, _format_show_value(value)))
    return rows


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        cap = get(args.model_id)
    except ModelNotFoundError:
        print(f"error: model not found: {args.model_id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(cap.to_dict(), ensure_ascii=False, indent=2))
        return 0
    rows = _iter_show_rows(cap.to_dict())
    width = max(len(key) for key, _ in rows)
    for key, value in rows:
        print(f"{key:<{width}}  {value}")
    return 0


def _finish(caps: list[Capability], args: argparse.Namespace, subject: str) -> int:
    """Shared tail for ``list``/``search``: no-match handling and rendering."""
    if not caps:
        print(f"error: no models matching {subject}", file=sys.stderr)
        _emit(caps, args)
        return 0 if getattr(args, "allow_empty", False) else 1
    return _emit(caps, args)


def _cmd_list(args: argparse.Namespace) -> int:
    caps = list_models(args.provider, include_deprecated=args.include_deprecated)
    _sort_caps(caps, args.sort)
    if args.limit is not None:
        caps = caps[: args.limit]
    if args.provider:
        subject = f"provider: {args.provider}"
    else:
        subject = "the catalog"
    return _finish(caps, args, subject)


def _cmd_search(args: argparse.Namespace) -> int:
    # limit is applied after sorting, so ask the registry for the full set.
    caps = search(
        args.prefix,
        provider=args.provider,
        include_deprecated=args.include_deprecated,
        limit=None,
    )
    _sort_caps(caps, args.sort)
    if args.limit is not None:
        caps = caps[: args.limit]
    return _finish(caps, args, f"prefix: {args.prefix}")


_TRUE_WORDS = {"true", "yes", "y", "t", "1", "on"}
_FALSE_WORDS = {"false", "no", "n", "f", "0", "off"}


def _parse_feature_tokens(tokens: Sequence[str]) -> dict[str, bool]:
    """Parse ``NAME``/``NAME=BOOL`` feature filters for ``llmcapa find``."""
    flags: dict[str, bool] = {}
    for token in tokens:
        name, sep, raw = token.partition("=")
        name = name.strip().replace("-", "_")
        if not name:
            raise ValueError(token)
        if not sep:
            flags[name] = True
            continue
        word = raw.strip().lower()
        if word in _TRUE_WORDS:
            flags[name] = True
        elif word in _FALSE_WORDS:
            flags[name] = False
        else:
            raise ValueError(raw)
    return flags


def _cmd_find(args: argparse.Namespace) -> int:
    try:
        flags = _parse_feature_tokens(args.features)
    except ValueError as e:
        print(f"error: invalid feature filter: {e}", file=sys.stderr)
        return 2
    caps = find(
        provider=args.provider,
        min_context_window=args.min_context,
        min_max_output_tokens=args.min_max_output,
        include_deprecated=args.include_deprecated,
        **flags,
    )
    _sort_caps(caps, args.sort)
    if args.limit is not None:
        caps = caps[: args.limit]
    if flags:
        subject = " ".join(f"{name}={value}" for name, value in sorted(flags.items()))
    elif args.provider:
        subject = f"provider: {args.provider}"
    else:
        subject = "the catalog"
    return _finish(caps, args, subject)


def _cmd_providers(_args: argparse.Namespace) -> int:
    for name in providers():
        print(name)
    return 0


def _cmd_tokens(args: argparse.Namespace) -> int:
    text = args.text
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()

    try:
        if args.messages:
            import json as _json

            try:
                msgs = _json.loads(text or "[]")
            except json.JSONDecodeError as e:
                print(f"error: invalid JSON: {e}", file=sys.stderr)
                return 1
            total = count_messages_tokens(msgs, args.model_id)
            print(total)
        elif text:
            total = count_tokens(text, args.model_id)
            print(total)
        else:
            print("error: provide text as argument or pipe via stdin", file=sys.stderr)
            return 1
    except ModelNotFoundError:
        print(f"error: model not found: {args.model_id}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_update(_args: argparse.Namespace) -> int:
    try:
        print("Fetching latest models from OpenRouter API...")
        count = default_registry().fetch_openrouter(cache_ttl=0)
        print(f"Successfully updated {count} models from OpenRouter.")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"error updating models: {e}", file=sys.stderr)
        return 1


def _cmd_fetch_hf(args: argparse.Namespace) -> int:
    try:
        print(
            f"Fetching top {args.limit} text-generation models from HuggingFace API..."
        )
        count = default_registry().fetch_huggingface(limit=args.limit, cache_ttl=0)
        print(f"Successfully registered {count} models from HuggingFace.")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"error fetching HuggingFace models: {e}", file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------


def _add_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv", "md", "markdown"),
        default=None,
        help="output format (default: table)",
    )
    parser.add_argument("--json", action="store_true", help="shortcut for --format json")
    parser.add_argument(
        "--columns",
        default=None,
        help="comma separated column list (e.g. provider,model_id,ctx,price)",
    )
    parser.add_argument(
        "--sort",
        default=None,
        help=(
            "comma separated sort keys; descending via ':desc' suffix or a "
            "'-' prefix (e.g. --sort='-ctx' or --sort=ctx:desc)"
        ),
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="maximum number of rows after sorting"
    )
    parser.add_argument(
        "--all",
        "--include-deprecated",
        dest="include_deprecated",
        action="store_true",
        help="include deprecated models (hidden by default)",
    )
    # Accepted for backwards compatibility; deprecated models are hidden by default.
    parser.add_argument(
        "--no-deprecated",
        dest="no_deprecated",
        action="store_true",
        help="deprecated alias (deprecated models are already hidden)",
    )
    parser.add_argument(
        "--wide", action="store_true", help="extra columns and no clipping"
    )
    parser.add_argument(
        "--width", type=int, default=None, help="table width budget for table output"
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="exit 0 even when nothing matched",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="llmcapa", description="Lookup LLM model capabilities (offline)."
    )
    parser.add_argument("--version", action="version", version=f"llmcapa {__version__}")
    parser.add_argument(
        "--extra",
        metavar="JSON_FILE",
        help="load extra model data from a local JSON file",
    )
    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="show capability of a model")
    p_show.add_argument("model_id")
    p_show.add_argument("--json", action="store_true", help="output as JSON")
    p_show.set_defaults(func=_cmd_show)

    p_list = sub.add_parser("list", help="list known models")
    p_list.add_argument("--provider", help="filter by provider")
    _add_render_options(p_list)
    p_list.set_defaults(func=_cmd_list)

    p_find = sub.add_parser(
        "find", help="find models by feature flags and size limits"
    )
    p_find.add_argument(
        "features",
        nargs="*",
        metavar="NAME[=BOOL]",
        help="feature filter, e.g. decision=true vision=yes; a bare NAME means true",
    )
    p_find.add_argument("--provider", help="filter by provider")
    p_find.add_argument(
        "--min-context",
        dest="min_context",
        type=int,
        default=0,
        help="minimum context window in tokens",
    )
    p_find.add_argument(
        "--min-max-output",
        dest="min_max_output",
        type=int,
        default=0,
        help="minimum max output tokens",
    )
    _add_render_options(p_find)
    p_find.set_defaults(func=_cmd_find)

    p_prov = sub.add_parser("providers", help="list known providers")
    p_prov.set_defaults(func=_cmd_providers)

    p_search = sub.add_parser("search", help="search models by prefix")
    p_search.add_argument(
        "prefix", help="prefix to match against model_id, display_name, or aliases"
    )
    p_search.add_argument("--provider", help="filter by provider")
    _add_render_options(p_search)
    p_search.set_defaults(func=_cmd_search)

    p_upd = sub.add_parser("update", help="fetch and update OpenRouter models cache")
    p_upd.set_defaults(func=_cmd_update)

    p_hf = sub.add_parser(
        "fetch-hf", help="fetch and register top models from HuggingFace"
    )
    p_hf.add_argument(
        "--limit", type=int, default=100, help="max models to fetch per pipeline tag"
    )
    p_hf.set_defaults(func=_cmd_fetch_hf)

    p_tok = sub.add_parser("tokens", help="count tokens for text or messages")
    p_tok.add_argument("model_id", help="model identifier")
    p_tok.add_argument(
        "text",
        nargs="?",
        default="",
        help="text to count, or JSON messages with --messages",
    )
    p_tok.add_argument(
        "--messages", action="store_true", help="treat input as JSON messages list"
    )
    p_tok.set_defaults(func=_cmd_tokens)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    if getattr(args, "no_deprecated", False) and not getattr(args, "include_deprecated", False):
        args.include_deprecated = False
    if args.extra:
        default_registry().load_extra(args.extra)
    try:
        return args.func(args)
    except ValueError as e:
        print(f"error: unknown option value: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
