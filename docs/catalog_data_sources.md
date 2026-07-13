# Catalog Data Sources

This document describes how each provider's catalog data is collected, including
any SSR (Server-Side Rendering) limitations and known issues.

---

## OpenAI

| Item | Detail |
|---|---|
| **Data file** | `src/llmcapa/data/openai.json` |
| **Method** | OpenRouter API (`https://openrouter.ai/api/v1/models`) |
| **SSR issue** | None. OpenRouter is an API-first service. |
| **Limitations** | OpenRouter's model list may lag behind OpenAI's latest releases. |
| **Script** | `scripts/_scrape_openai.py` (via OpenRouter) |

## Azure AI Foundry (Azure OpenAI + Direct from Azure)

| Item | Detail |
|---|---|
| **Data file** | `src/llmcapa/data/azure_foundry.json` |
| **Method** | Playwright scraping of `https://ai.azure.com/catalog/models` |
| **SSR issue** | **Yes.** The first page (top 51 models by popularity) is SSR'd directly into HTML. These models are **not** accessible via the `asset-gallery/v1.0/models` API. Clicking "Next" triggers the API for pages 2+. |
| **Affected models** | The most popular models (e.g. `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`, `gpt-5.4-mini`, `gpt-5.4-nano`) are on page 1 and invisible to API-only scrapers. |
| **Workaround** | The script scrapes the first page's DOM for model names, then visits each model's detail page individually for metadata. |
| **Script** | `scripts/_scrape_azure_catalog.py`, `scripts/_fetch_azure_catalog.py` |

## Ollama

| Item | Detail |
|---|---|
| **Data file** | `src/llmcapa/data/ollama.json` |
| **Method** | Internal Ollama API (`/api/tags` via `ollama list` command) |
| **SSR issue** | None for scraping. The web UI at `ollama.com/library` is SSR with 236 models on the initial page, but the internal API returns all models (`~1,638` as of 2026). |
| **Limitations** | Only includes models available through the Ollama CLI/library. No community forks. |
| **Script** | N/A (collected via `ollama list`). |

## HuggingFace

| Item | Detail |
|---|---|
| **Data file** | `src/llmcapa/data/huggingface.json` |
| **Method** | HuggingFace REST API (`https://huggingface.co/api/models`) |
| **SSR issue** | The web UI (`huggingface.co/models`) uses SSR with URL-based pagination (`?p=0..99`, 30 models/page). This could theoretically miss models on pages >100. However, the **REST API** uses cursor-based pagination which accesses **all models** without limitation, so there is no SSR issue for API scrapers. |
| **Filter** | Only `pipeline_tag=text-generation` models with >= 5,000 downloads are collected. |
| **Metadata limit** | Context window, max tokens, and modality information are **not available** from the API. Defaults are used. |
| **Script** | `scripts/_scrape_huggingface.py` |

## Other Providers

| Provider | Method | SSR issue |
|---|---|---|
| Anthropic | API | None |
| Google (Gemini) | API | None |
| DeepSeek | Web scraping | None |
| xAI (Grok) | API | None |
| Moonshot (Kimi) | Web scraping | None |
| NVIDIA | API | None |
| Novita | API | None |
| Qwen | Web scraping | None |

---

## Summary of SSR Issues

Only **Azure AI Foundry** has a meaningful SSR issue where popular models are hidden
from the API. All other providers use standard APIs or pagination that can be
iterated without gaps.

For HuggingFace, while the web UI has SSR pagination, the official REST API
provides complete access and is the recommended data source.
