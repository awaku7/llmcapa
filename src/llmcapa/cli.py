"""Command line interface for llmcapa.

Usage:
    llmcapa show <model_id> [--json]
    llmcapa list [--provider NAME] [--json] [--no-deprecated]
    llmcapa providers
    llmcapa search <prefix> [--provider NAME] [--json] [--no-deprecated] [--limit N]
    llmcapa update
    llmcapa fetch-hf [--limit N]
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import (
    __version__,
    count_messages_tokens,
    count_tokens,
    get,
    list_models,
    providers,
    search,
)
from .registry import ModelNotFoundError, default_registry


def _print_table(rows: List[List[str]], headers: List[str]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join("{:<%d}" % w for w in widths)
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))


def _cmd_show(args: argparse.Namespace) -> int:
    try:
        cap = get(args.model_id)
    except ModelNotFoundError:
        print(f"error: model not found: {args.model_id}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(cap.to_dict(), ensure_ascii=False, indent=2))
    else:
        d = cap.to_dict()
        width = max(len(k) for k in d)
        for key, value in d.items():
            print(f"{key:<{width}}  {value}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    caps = list_models(args.provider, include_deprecated=not args.no_deprecated)
    if args.json:
        print(json.dumps([c.to_dict() for c in caps], ensure_ascii=False, indent=2))
        return 0
    rows = []
    for c in caps:
        rows.append([
            c.provider,
            c.model_id,
            str(c.context_window),
            str(c.max_output_tokens),
            "yes" if c.supports_vision else "no",
            "yes" if c.supports_function_calling else "no",
            "yes" if c.deprecated else "no",
        ])
    _print_table(rows, ["provider", "model_id", "context", "max_out", "vision", "tools", "deprecated"])
    return 0


def _cmd_providers(_args: argparse.Namespace) -> int:
    for name in providers():
        print(name)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    caps = search(
        args.prefix,
        provider=args.provider,
        include_deprecated=not args.no_deprecated,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([c.to_dict() for c in caps], ensure_ascii=False, indent=2))
        return 0
    if not caps:
        print(f"no models matching prefix: {args.prefix}", file=sys.stderr)
        return 1
    rows = []
    for c in caps:
        rows.append([
            c.provider,
            c.model_id,
            str(c.context_window),
            str(c.max_output_tokens),
            "yes" if c.supports_vision else "no",
            "yes" if c.supports_function_calling else "no",
            "yes" if c.deprecated else "no",
        ])
    _print_table(rows, ["provider", "model_id", "context", "max_out", "vision", "tools", "deprecated"])
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
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def _cmd_update(_args: argparse.Namespace) -> int:
    try:
        print("Fetching latest models from OpenRouter API...")
        count = default_registry().fetch_openrouter(cache_ttl=0)
        print(f"Successfully updated {count} models from OpenRouter.")
        return 0
    except Exception as e:
        print(f"error updating models: {e}", file=sys.stderr)
        return 1


def _cmd_fetch_hf(args: argparse.Namespace) -> int:
    try:
        print(f"Fetching top {args.limit} text-generation models from HuggingFace API...")
        count = default_registry().fetch_huggingface(limit=args.limit, cache_ttl=0)
        print(f"Successfully registered {count} models from HuggingFace.")
        return 0
    except Exception as e:
        print(f"error fetching HuggingFace models: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmcapa", description="Lookup LLM model capabilities (offline).")
    parser.add_argument("--version", action="version", version=f"llmcapa {__version__}")
    parser.add_argument("--extra", metavar="JSON_FILE", help="load extra model data from a local JSON file")
    sub = parser.add_subparsers(dest="command")

    p_show = sub.add_parser("show", help="show capability of a model")
    p_show.add_argument("model_id")
    p_show.add_argument("--json", action="store_true", help="output as JSON")
    p_show.set_defaults(func=_cmd_show)

    p_list = sub.add_parser("list", help="list known models")
    p_list.add_argument("--provider", help="filter by provider")
    p_list.add_argument("--json", action="store_true", help="output as JSON")
    p_list.add_argument("--no-deprecated", action="store_true", help="hide deprecated models")
    p_list.set_defaults(func=_cmd_list)

    p_prov = sub.add_parser("providers", help="list known providers")
    p_prov.set_defaults(func=_cmd_providers)

    p_search = sub.add_parser("search", help="search models by prefix")
    p_search.add_argument("prefix", help="prefix to match against model_id, display_name, or aliases")
    p_search.add_argument("--provider", help="filter by provider")
    p_search.add_argument("--json", action="store_true", help="output as JSON")
    p_search.add_argument("--no-deprecated", action="store_true", help="hide deprecated models")
    p_search.add_argument("--limit", type=int, default=None, help="maximum number of results")
    p_search.set_defaults(func=_cmd_search)

    p_upd = sub.add_parser("update", help="fetch and update OpenRouter models cache")
    p_upd.set_defaults(func=_cmd_update)

    p_hf = sub.add_parser("fetch-hf", help="fetch and register top models from HuggingFace")
    p_hf.add_argument("--limit", type=int, default=100, help="max models to fetch per pipeline tag")
    p_hf.set_defaults(func=_cmd_fetch_hf)

    p_tok = sub.add_parser("tokens", help="count tokens for text or messages")
    p_tok.add_argument("model_id", help="model identifier")
    p_tok.add_argument("text", nargs="?", default="", help="text to count, or JSON messages with --messages")
    p_tok.add_argument("--messages", action="store_true", help="treat input as JSON messages list")
    p_tok.set_defaults(func=_cmd_tokens)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.extra:
        default_registry().load_extra(args.extra)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
