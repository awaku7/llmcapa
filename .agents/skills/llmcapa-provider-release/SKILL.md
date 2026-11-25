---
name: llmcapa-provider-release
description: Refresh, validate, version, build, and publish the llmcapa provider catalog package. Use when updating provider catalogs or carrying out an llmcapa release to PyPI.
---

# llmcapa provider catalog and release workflow

Use this skill for `llmcapa` catalog refreshes and package releases. Preserve existing user changes, use provider-specific official sources, and never invent catalog values or print credentials.

## 1. Inspect the workspace first

- Check `git status`, current branch, and existing staged/unstaged changes before editing or refreshing anything.
- Never reset, restore, stash-pop, or overwrite pre-existing work to get a clean tree. `scripts/refresh_catalogs.py` requires no unstaged tracked edits; if the workspace is dirty, pause and preserve the changes (use a separate worktree if appropriate).
- A staged refresh can be resumed only when its staged files are known to be catalog-refresh outputs, using `--resume-staged-catalogs`. Do not use that flag to bypass unrelated staged changes.

## 2. Refresh providers one at a time

- List available updaters with `python scripts/_update_all_providers.py --list`.
- Refresh sequentially with the report-producing runner:

  ```powershell
  python scripts/refresh_catalogs.py --timeout-seconds 300
  ```

  For a legitimate interrupted run with only previously staged catalog changes, add `--resume-staged-catalogs`.
- Each provider has a provider-specific updater. Do not source native-provider catalogs from OpenRouter; OpenRouter may populate only `openrouter.json`.
- Review `outputs/catalog_refresh/report.md`, `report.json`, and `logs/<provider>.log`. Check added/modified/removed counts and failures. Failed refreshes should retain prior data; do not replace missing data with guesses. If a public upstream source starts requiring authentication (for example, a spreadsheet returning 401), record it as blocked and retry only after the source is accessible.
- The runner validates duplicate/missing model IDs, suspicious mass deletions, lost known capabilities/prices, and JSON/SQLite update consistency. It also includes the last updater diagnostic in the report on failure.

## 3. Check catalog consistency and size

Run the parity checker and full test suite after refresh:

```powershell
python scripts/verify_catalog_parity.py
$env:PYTHONPATH = "src;$env:PYTHONPATH"
python -m pytest -q
```

Compare updated JSON sizes against the repository baseline (`HEAD`/`origin/main` at task start), not just absolute sizes. Investigate large percentage and byte increases; large provider catalogs such as Hugging Face can naturally be tens of megabytes. Do not pretty-print catalog JSON or remove records solely to reduce file size.

## 4. Bump version consistently

When asked to bump the package version, update both:

- `[project].version` in `pyproject.toml`
- the source-tree `__version__` fallback in `src/llmcapa/__init__.py`

Keep them identical. Parse `pyproject.toml` and verify the fallback before building. Do not change the version unless requested or part of an explicitly requested release.

## 5. Build and validate distributions

Build from the committed/validated source state, then check the exact versioned artifacts:

```powershell
python -m build
python -m twine check dist/llmcapa-<VERSION>-py3-none-any.whl dist/llmcapa-<VERSION>.tar.gz
```

Confirm the target version is not already published at `https://pypi.org/pypi/llmcapa/<VERSION>/json` before uploading. Do not use a wildcard that could include older distributions.

## 6. Publish to PyPI only when explicitly requested

`LLMCAPA_TOKEN` is a secret. Never print it, include it in a message, or embed it in command text. On Windows, when using `pwsh_exec`, set Twine credentials through process environment variables—do not use CMD `set` syntax in PowerShell:

```powershell
if ([string]::IsNullOrWhiteSpace($env:LLMCAPA_TOKEN)) { throw "LLMCAPA_TOKEN is not set" }
$env:TWINE_USERNAME = '__token__'
$env:TWINE_PASSWORD = $env:LLMCAPA_TOKEN
if ($env:TWINE_PASSWORD -cne $env:LLMCAPA_TOKEN) { throw "Twine token environment setup failed" }
python -m twine upload --non-interactive --disable-progress-bar `
  dist/llmcapa-<VERSION>-py3-none-any.whl dist/llmcapa-<VERSION>.tar.gz
```

A 403 may be caused by incorrectly set shell environment variables, not necessarily a revoked token. First verify only booleans/equality (never values) in the same shell, then retry correctly once. If a correctly passed token still receives 403, stop and ask the user to check PyPI token scope/project permissions; do not repeatedly retry. After a successful upload, verify the release JSON endpoint returns the expected version.

## 7. Git operations

Stage only intended catalog, source, test, and distribution-version files. Review the staged diff and run a secret scan before committing. Commit and push only when the user explicitly asks. Do not stage editor/tool-generated `.org` backups or unrelated files.
