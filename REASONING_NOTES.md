# llmcapa: Research Notes (reasoning_effort / thinking_budget)

> 調査日: 2026-07-10
> 各プロバイダの reasoning_effort / thinking_budget 対応値の公式情報源

---

## OpenAI

| モデル | reasoning_effort 値 | 出典 |
|---|---|---|
| o1, o3, o4, gpt-5, gpt-5.1 | none, low, medium, high | https://developers.openai.com/api/docs/models/gpt-5.1 |
| gpt-5.1-codex-max, gpt-5.2+ | none, low, medium, high, xhigh | https://developers.openai.com/api/docs/models/gpt-5.4 |
| gpt-5.4-pro, gpt-5.5, gpt-5.5-pro | none, low, medium, high, xhigh | https://developers.openai.com/api/docs/models/gpt-5.4 |
| gpt-5.6 (Luna/Sol/Terra) | none, low, medium, high, xhigh, max | https://developers.openai.com/api/docs/guides/latest-model |
| 注意: minimal は汎用API Referenceにはあるが、モデル別ドキュメントで確認できず | | https://developers.openai.com/api/docs/guides/reasoning |

## Anthropic (Claude)

| モデル | パラメータ | 値 | 出典 |
|---|---|---|---|
| Claude Opus 4.6+, Fable 5 | effort (reasoning_effort) | low, medium, high, max | https://platform.claude.com/docs/en/build-with-claude/effort |
| Claude Sonnet 4.6, Sonnet 5 | effort (reasoning_effort) | low, medium, high | https://platform.claude.com/docs/en/build-with-claude/effort |
| Claude 4 以前 | thinking_budget (budget_tokens) | token_range (min: 1024, max: 128000) | https://docs.aws.amazon.com/bedrock/latest/userguide/claude-messages-extended-thinking.html |

## Google Gemini

| モデル | パラメータ | 値 | 出典 |
|---|---|---|---|
| Gemini 2.5 Flash/Pro | thinking_level / reasoning_effort | none, low, medium, high | https://ai.google.dev/gemini-api/docs/gemini-3 |
| Gemini 3 Flash | thinking_level / reasoning_effort | none, low, medium, high | https://discuss.ai.google.dev/t/117875 |
| Gemini 3 Pro | thinking_level / reasoning_effort | none, low, medium, high | https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/start/get-started-with-gemini-3 |

## xAI (Grok)

| モデル | 値 | 出典 |
|---|---|---|
| Grok 4.5 | none, low, medium, high | https://docs.x.ai/developers/model-capabilities/text/reasoning |
| Grok 4.3 | none, low, medium, high | https://www.promptfoo.dev/docs/providers/xai/ |

## Mistral

| モデル | 値 | 出典 |
|---|---|---|
| Mistral Small 4 | none, low, medium, high | https://mistral.ai/news/mistral-small-4/ |

## MiniMax

| モデル | 値 | 出典 |
|---|---|---|
| MiniMax M1/M2 | low, medium, high | https://github.com/MiniMax-AI/MiniMax-M2/issues/52 |
| MiniMax M3 | low, medium, high | https://platform.minimax.io/docs/token-plan/codex |
| 注意: none は明示的に言及なし | | |

## Moonshot (Kimi) - Updated 2026-07-10

| モデル | 値 | 出典 |
|---|---|---|
| Kimi K2 | low, medium, high | https://github.com/NousResearch/hermes-agent/issues/32223 (api.moonshot.ai uses low|medium|high) |
| Kimi K2.5 | low, medium, high | https://repost.aws/ja/questions/... (Bedrock: high,low,medium,minimal) |
| Kimi K2.6 | none, low, medium, high | https://replicate.com/moonshotai/kimi-k2.6 |
| Kimi K2.7 Code | none, low, medium, high | platform.kimi.ai docs (推定) |
| 注意: K2 は none/minimal 非サポート。K2.6 以降は none サポート | | |

## DeepSeek

| モデル | パラメータ | 値 | 出典 |
|---|---|---|---|
| DeepSeek V4 Pro/Flash | reasoning_effort | none, low, medium, high, xhigh, max | https://github.com/BerriAI/litellm/issues/27439 |
| DeepSeek R1 | thinking_budget | token_range | https://api-docs.deepseek.com/guides/thinking_mode |

## NVIDIA Nemotron

| モデル | 値 | 出典 |
|---|---|---|
| Nemotron-3-Nano | none, low | https://github.com/openclaw/openclaw/issues/15299 |
| Nemotron-3-Super | none, low, medium, high | https://dev.classmethod.jp/articles/dgx-spark-nemoclaw-openshell-handson/ |
| Nemotron-3-Ultra | none, low, medium, high (推定) | Baseten docs に記載あるが未確 |

## Qwen

| モデル | 値 | 出典 |
|---|---|---|
| Qwen3 全般 | none, low, medium, high | https://docs.venice.ai/guides/features/reasoning-models |

## Sakana Fugu

| モデル | 値 | 出典 |
|---|---|---|
| Fugu | high, xhigh, max | https://feelflow.net/blog/2026-06-sakana-fugu-codex-claude-code-copilot-setup |
| Fugu Ultra | high, xhigh, max (low/medium は 400 エラー) | https://pi.dev/packages/pi-sakana-provider |

## Novita AI (プロキシ型)

| モデルプレフィックス | 値 | 根拠 |
|---|---|---|
| openai/* | none, low, medium, high | OpenAI API 互換 |
| google/* | none, low, medium, high | Google API 互換 |
| minimax/* | low, medium, high | MiniMax 互換 |
| qwen/* | none, low, medium, high | Qwen 互換 |
| deepseek/* | none, low, medium, high, xhigh, max | DeepSeek 互換 |
| zai-org/* (GLM) | none, low, medium, high | GLM 互換 |

## OpenRouter (プロキシ型・正規化)

| 対象 | 値 | 出典 |
|---|---|---|
| 全モデル（API enum） | none, minimal, low, medium, high, xhigh | https://openrouter.ai/docs/api/reference/parameters |
| max | 一部モデル固有値。一般enumには含まれない | https://openrouter.ai/docs/guides/best-practices/reasoning-tokens |

## Ollama (ローカル)

| モデル | 値 | 出典 |
|---|---|---|
| DeepSeek R1/R2 全variant | none, low, medium, high, max | https://docs.ollama.com/api/openai-compatibility |
| Qwen3 全variant | none, low, medium, high | Ollama OpenAI互換API docs |
