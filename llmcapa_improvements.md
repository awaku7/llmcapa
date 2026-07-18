# llmcapa Improvement Requests

> **Status vs local source 0.4.0 (2026-07-18)**
>
> | # | Topic | Status |
> |---|---|---|
> | 1 | Missing providers (`lmstudio`, `hf`, `sakura`) | **Done** — `lmstudio` + `sakura` bundled; `hf` → `huggingface`; `lm-studio`/`lm_studio` → `lmstudio` |
> | 2 | Mismatched provider names (aliases) | **Done** — `_provider_aliases` (bedrock, gemini, vertexai, grok, moonshot, mimo, alibaba/dashscope→qwen, …) |
> | 3 | Provider name normalization | **Done** — lower + unify `_. \t` → `-` |
> | 4 | Incomplete capability flags | **Open** |
> | 5 | Multi-provider model discovery | **Partial** — `search(provider=None)` returns all provider-scoped matches; dedicated `find()` not added |
> | 6 | Model ID variations / short-name aliases | **Open** (model-level; separate from provider aliases) |
>
> Implemented details: see `provider_update_log.md` §0.4.0, `DEVELOP.md` §Provider Aliases.

## 1. Missing providers (not in llmcapa at all)

> **Status (0.4.0): DONE** — providers/aliases present in local source.

These uag providers were originally missing; current status:

| uag provider | Description | Notes |
|---|---|---|
| `lmstudio` | LM Studio — local model server | Bundled `lmstudio.json` catalog; aliases `lm-studio` / `lm_studio`. |
| `hf` | HuggingFace Inference API | Alias `hf` → `huggingface`. Catalog has popular HF models. |
| `sakura` | SAKURA AI Engine | Bundled `sakura.json` with `sakura-default` fallback. |

## 2. Mismatched provider names

> **Status (0.4.0): DONE** for rows below (see `_provider_aliases`), including `alibaba`/`dashscope` → `qwen`.


These uag providers exist in llmcapa but under a **different name**:

| uag provider | llmcapa provider | Models | Action |
|---|---|---|---|
| `bedrock` | `amazon` | 21 | Add `bedrock` as an alias for `amazon` |
| `gemini` | `google` | 75 | Add `gemini` as an alias for `google` |
| `vertexai` | `google` | 75 | Add `vertexai` as an alias for `google` |
| `grok` | `xai` | 18 | Add `grok` as an alias for `xai` |
| `alibaba` | `qwen` | 143 | Add `alibaba` as an alias for `qwen` |
| `moonshot` | `moonshotai` | 15 | Add `moonshot` as an alias for `moonshotai` |
| `mimo` | `xiaomi` | 5 | Add `mimo` as an alias for `xiaomi` |

**Expected behavior**: `llmcapa.get("gpt-4o", provider="bedrock")` should resolve to
the same capability as `llmcapa.get("gpt-4o", provider="amazon")`.

## 3. Provider name normalization

> **Status (0.4.0): DONE** — case-insensitive + separator unification implemented.


llmcapa provider names use inconsistent casing and separators:

- `azure-openai` (kebab-case)
- `bytedance-seed` (kebab-case)
- `anthracite-org` (kebab-case)
- `cognitivecomputations` (no separator)
- `inclusionai` (no separator)

Suggestion: accept lookups case-insensitively and treat hyphens/underscores as optional
separators so that `provider="azure_openai"` and `provider="azureopenai"` also work.

## 4. Incomplete capability flags

Several models have `supports_function_calling=None` or `supports_vision=None`
where the capability is known to exist:

| Model | Known capability | llmcapa value |
|---|---|---|
| `Llama-3.2-90B-Vision-Instruct` | vision=True, fc=True | vision=False, fc=None |
| `Llama-4-Scout-17B-16E` | vision=True, fc=True | vision=False, fc=None |
| `Codestral-2501` | fc=True | fc=None |
| `mistral-small` | vision=False (text-only) | vision=False ✓ |

Suggestion: fill `None` → `True`/`False` where the information is publicly documented.
Treat `None` as "unknown" only when truly uncertain.

## 5. Model ID discovery from API responses

> **Status (0.4.0): PARTIAL** — `search(model_id)` without provider returns all provider-scoped hits. A dedicated `find()` API was not added.


When uag calls `llmcapa.get(model_id)` without a provider, the first-registered
(native) version is returned. However, the same model_id may exist under multiple
providers with different specs (e.g. `gpt-4o` under both `openai` and `azure-openai`).

Suggestion: add a `find(model_id)` method that returns a list of `(provider, Capability)`
tuples for all matches, allowing the caller to pick the right one.

## 6. Model ID variations

Some models are known by different IDs across providers:

| uag usage | llmcapa model_id |
|---|---|
| `DeepSeek-V3` | `DeepSeek-V3-0324` |
| `gpt-4o-mini` | not in `openai` provider (only `gpt-4o-mini-transcribe` exists) |
| `o3-mini` | `openai/o3-mini` (with `openai/` prefix) |

Suggestion: maintain an alias table so that common short names resolve correctly.

## 7. Implementation notes

- llmcapa version at time of writing: **0.3.0** (this doc); local source now **0.4.0**
- uag provider list source: `AGENTS.md` and `src/uagent/providers/provider_caps.py`
- Test file: `tests/test_llmcapa.py` (37 tests covering all 70 llmcapa providers)
