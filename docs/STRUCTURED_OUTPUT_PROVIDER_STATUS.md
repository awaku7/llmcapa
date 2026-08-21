# Structured Output 対応状況

最終確認日: 2026-08-21

## 概要

`supports_json_mode` と `supports_json_schema` は、公式 API ドキュメントで根拠を確認できた場合だけモデルデータへ反映する。OpenRouter や第三者カタログによる推測値で、各プロバイダーの公式カタログを上書きしない。

確認・更新用スクリプト:

```text
scripts/_update_structured_output_providers.py
```

実行例:

```bash
python scripts/_update_structured_output_providers.py --insecure
```

`--insecure` は、実行環境の証明書検証問題を回避するための実行時オプションであり、スクリプトの恒久的な SSL 無効化ではない。

## モデル単位で JSON Schema 対応を反映済み

| プロバイダー | true 件数 | モデル件数 | 根拠 |
|---|---:|---:|---|
| ByteDance Seed | 6 | 8 | Volcengine Ark Chat API の `response_format` / `json_schema` |
| llama.cpp | 1,634 | 1,634 | LM Studio OpenAI 互換 Structured Output API。モデル単位の実装は実行環境依存 |
| LM Studio | 105 | 105 | `/v1/chat/completions` の `response_format.type=json_schema` |
| Morph | 10 | 12 | Fast Modelsの公式カタログ。Fast Applyの`morph-v3-*`は別カテゴリ |
| Ollama | 1,653 | 1,653 | ローカル Ollama API の `format` JSON Schema 対応。Ollama Cloud は非対応 |
| OpenRouter | 346 | 563 | API の `supported_parameters` に `structured_outputs` があるモデル |
| Perplexity | 5 | 7 | Sonar API の `response_format` / `json_schema` |
| Sakana AI | 5 | 5 | Chat Completions / Responses API の `json_object` / `json_schema` |
| Inception | 1 | 1 | Mercury 2 Chat Completions の `response_format.type=json_schema` |
| Writer | 1 | 1 | Palmyra X4/X5 Chat API の `response_format.json_schema` |

## JSON Mode は確認済みだが JSON Schema は未確定

### Z.ai

公式 Structured Output ドキュメントで以下のモデルの JSON Mode を確認済み:

- GLM-4.5
- GLM-4.6
- GLM-4.7
- GLM-5

設定:

```json
"supports_json_mode": true,
"supports_json_schema": null
```

Z.ai の公式例は `response_format={"type":"json_object"}` を使う。JSON Schema はアプリケーション側の `jsonschema.validate()` の例であり、API の `response_format.type=json_schema` 対応としては確認していない。

## API 機能としては確認済みだが、モデル単位では未確定

### Vercel

Vercel AI SDK / AI Gateway の公式ドキュメントで以下を確認済み:

- `generateObject`
- `streamObject`
- OpenAI 互換 `response_format.type=json_schema`

ただし `vercel.json` は複数プロバイダーのモデルを含む集約カタログであり、全モデルへの一律 `true` 設定は行っていない。

## 公式出典は登録済みだが、JSON Schema 対応を確認できていない

以下は公式 URL の到達確認と出典情報の記録まで完了しているが、モデル出力 API の `response_format.type=json_schema` を確認できていない。

- AI21
- AllenAI
- Arcee AI
- CognitiveComputations
- NousResearch
- Poolside
- Relace
- Thinking Machines
- Mancer
- Nex-AGI
- Perceptron
- Undi95
- Hugging Face 集約カタログ

### 追加確認した公式サイト

以下の公式サイトは到達確認済み。ただし、今回の確認ではモデル出力APIのJSON Schema対応を明記した根拠がないため、フラグは変更していない。

| プロバイダー | 公式URL | 確認結果 |
|---|---|---|
| AI21 | https://docs.ai21.com/docs/overview | Jamba APIモデル（`jamba-large` / `jamba-mini`等）を追加。`json_object`のみ、JSON Schemaは未確認 |
| Arcee AI | https://docs.arcee.ai/ | API公開モデル`trinity-mini` / `trinity-large-preview`を追加。Structured Outputsは`json_object`のみ |
| AllenAI | https://docs.allenai.org/ | モデル・データセット文書。推論APIのJSON Schemaは未確認 |
| Poolside | https://docs.poolside.ai/ | `laguna-m-1`を追加。API例はChat Completions・Tools等で、`response_format` / JSON Schemaは未確認 |
| Relace | https://docs.relace.ai/docs/introduction | OpenAPIはKimi K3限定の `json_object`。JSON Schemaは未確認 |
| Thinking Machines | https://thinkingmachines.ai/ | 企業・研究情報。公開APIのJSON Schema仕様は未確認 |

### AI21 の補足

AI21 の HTTP Tools ドキュメントには、ツール入力の `function.parameters` に JSON Schema を使う記載がある。しかし、これはツール入力用であり、モデル出力の Structured Output API ではない。そのため `supports_function_calling=true` の根拠にはなるが、`supports_json_schema=true` にはしていない。

### Ollama の補足

公式ドキュメントはローカル API の Structured Outputs をサポートする一方、Ollama Cloud は現在非対応と明記している。カタログの `true` はローカル API の範囲である。

## 未確定値の扱い

公式 API のモデル単位の根拠がない場合:

```json
"supports_json_schema": null
```

`null` は非対応を意味しない。公式情報が不足しているため未確認であることを意味する。

## 検証結果

全テスト:

```text
12829 passed
```
