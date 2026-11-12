"""Compare first lookup in fresh processes using the installed llmcapa wheel."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import tracemalloc


def measure(mode, model, provider):
    from llmcapa.registry import Registry

    tracemalloc.start()
    start = time.perf_counter()
    registry = Registry()
    if mode == "json":
        registry._load_bundled_files()
        registry._loaded = True
    capability = registry.get(model, provider)
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    if mode == "sqlite" and registry._catalog_index is None:
        raise RuntimeError("SQLite is not active; install a fresh llmcapa wheel")
    print(
        json.dumps(
            {
                "mode": mode,
                "model": capability.model_id,
                "provider": capability.provider,
                "seconds": elapsed,
                "peak_python_mib": peak / (1024**2),
            }
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model")
    parser.add_argument("--provider")
    parser.add_argument("--worker", choices=("json", "sqlite"))
    args = parser.parse_args()
    if args.worker:
        measure(args.worker, args.model, args.provider)
        return
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home, USERPROFILE=home)
        for mode in ("sqlite", "json"):
            command = [
                sys.executable,
                __file__,
                args.model,
                "--worker",
                mode,
            ]
            if args.provider:
                command.extend(["--provider", args.provider])
            subprocess.run(command, env=env, check=True)


if __name__ == "__main__":
    main()
