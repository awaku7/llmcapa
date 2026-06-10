"""Command line interface for llmcapa.

Usage:
    llmcapa show <model_id> [--json]
    llmcapa list [--provider NAME] [--json] [--no-deprecated]
    llmcapa providers
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__, get, list_models, providers
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


def _cmd_update(_args: argparse.Namespace) -> int:
    try:
        print("Fetching latest models from OpenRouter API...")
        # Force fetch by passing cache_ttl=0 or None (we want to update the cache)
        count = default_registry().fetch_openrouter(cache_ttl=0)
        print(f"Successfully updated {count} models from OpenRouter.")
        return 0
    except Exception as e:
        print(f"error updating models: {e}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llmcapa", description="Lookup LLM model capabilities (offline).")
    parser.add_argument("--version", action="version", version=f"llmcapa {__version__}")
    parser.add_argument("--extra", metavar="JSON_FILE", help="load extra model data from a local JSON file")
    parser.add_argument("--fetch-openrouter", action="store_true", help="fetch all models dynamically from OpenRouter API")
    parser.add_argument("--clear-cache", action="store_true", help="clear local OpenRouter cache file")
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

    p_upd = sub.add_parser("update", help="fetch and update OpenRouter models cache")
    p_upd.set_defaults(func=_cmd_update)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.clear_cache:
        import os
        home = os.path.expanduser("~")
        cache_file = os.path.join(home, ".llmcapa", "openrouter_cache.json")
        if os.path.exists(cache_file):
            try:
                os.remove(cache_file)
                print("Local OpenRouter cache cleared.")
            except Exception as e:
                print(f"error clearing cache: {e}", file=sys.stderr)
                return 1
        else:
            print("No local cache found.")
    if args.extra:
        default_registry().load_extra(args.extra)
    if args.fetch_openrouter:
        try:
            # Use a default TTL of 24 hours (86400 seconds) for CLI to avoid hitting API limits
            default_registry().fetch_openrouter(cache_ttl=86400)
        except Exception as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
