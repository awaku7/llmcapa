# llmcapa

さまざまなLLMモデルの機能（コンテキストウィンドウ、モダリティ、サポートされている機能など）を検索するためのライブラリです。デフォルトで完全にオフラインで動作し、必要に応じてOpenRouterから最新モデルのデータを取得・キャッシュして更新することも可能です。

## 特徴

- **包括的な同梱データ**: OpenAI、Anthropic、Google (Gemini)、Microsoft (Phi)、Amazon (Nova/Titan)、Meta (Llama)、Mistral、Qwen、DeepSeek、NVIDIA、および日本の国内モデル（デジタル庁の「GENNAI」プラットフォームで採用されているNTT tsuzumi、PFN PLaMo、ELYZA、SoftBank、NEC、Fujitsuなど）のオフライン機能データを同梱しています。
- **実行時依存関係ゼロ**: Python標準ライブラリのみで動作します。外部パッケージ（`pytest` や `build` など）は開発・テスト用のみです。
- **エイリアス解決**: エイリアスやプロバイダー固有の名前を自動的に解決します（例: `gpt-4o-2024-08-06` -> `gpt-4o`、`gemini-1.5-pro-preview-0409` -> `gemini-1.5-pro`）。
- **高度な機能クエリ**: `vision`、`multimodal`、`chat_completion`、`responses_api`、`reasoning_effort`、`thinking_budget`、および特定の入力/出力モダリティ（例: `image_input`、`image_output`、`audio_input`）のサポート状況を確認できます。
- **高いパフォーマンス**: 評価された機能チェックは、冗長な計算を避けるためにメモ化（内部キャッシュ）されます。
- **コスト見積もり**: 入力および出力トークン数に基づいてAPIコストを見積もります。
- **代替モデルチェッカー**: コンテキストウィンドウと必要な機能に基づいて、あるモデルを別のモデルで安全に代替できるかどうかを確認します。
- **トークナイザーマッピング**: モデルの機能から直接トークナイザー名（例: `o200k_base`）にアクセスできます。
- **動的なOpenRouter連携**: OpenRouter APIから300以上のモデルを動的に取得して登録できます。ローカルファイルキャッシュにより、最新の更新を反映したオフライン利用が可能です。
- **拡張性**: 独自のローカルJSONモデル定義をロードできます。
- **CLI同梱**: ターミナルから直接モデルの機能を照会・一覧表示できます。

## インストール

```bash
pip install llmcapa
```

またはソースからインストール:

```bash
pip install .
```

## 使い方

### 基本的な検索

```python
import llmcapa

# モデルの機能を取得（大文字小文字を区別せず、エイリアスも解決されます）
cap = llmcapa.get("gpt-4o")
print(cap.context_window)       # 128000
print(cap.max_output_tokens)    # 16384
print(cap.tokenizer_name)       # "o200k_base"

# 機能のサポート状況を確認
print(cap.supports("vision"))            # True
print(cap.supports("responses_api"))     # True
print(cap.supports("reasoning_effort"))  # False

# サポートされているすべての機能を一覧表示
print(cap.features())
# ['chat_completion', 'function_calling', 'image', 'image_input', 'image_output', 'json_mode', 'multimodal', 'responses_api', 'streaming', 'text', 'text_input', 'text_output', 'vision']
```

### トークン数とコストの見積もり

指定されたテキストのトークン数（30以上の主要言語に対応）を推定し、APIコストを計算します。

```python
gpt = llmcapa.get("gpt-4o")

# 多言語テキストのトークン数を推定
# `tiktoken` がインストールされている場合、OpenAIモデルに対して自動的にそれを使用して正確なトークン数を算出します。
# インストールされていない場合は、標準ライブラリのみの高度な簡易推定にフォールバックします。
text = "Hello world! こんにちは世界。"
tokens = gpt.estimate_tokens(text)
print(tokens)  # 10 (推定トークン数)

# トークン数に基づいてAPIコストを見積もり（コストと通貨を返します）
res = gpt.estimate_cost(input_tokens=1500, output_tokens=500)
print(res)  # {'cost': 0.00875, 'currency': 'USD'}
```

### 代替モデルチェッカー

あるモデルを別のモデルで安全に代替できるかどうかを確認します。代替モデルは、対象モデル以上のコンテキストウィンドウを持ち、必要なすべての機能をサポートしている必要があります。

```python
gpt4o = llmcapa.get("gpt-4o")
gpt4o_mini = llmcapa.get("gpt-4o-mini")
gemini = llmcapa.get("gemini-3.5-flash")

# gpt-4o-miniは同じコンテキストウィンドウを持ちますが、image_output（gpt-4oがサポート）がありません
print(gpt4o.can_be_replaced_by(gpt4o_mini))  # False

# gemini-3.5-flashはより大きなコンテキストウィンドウを持ちますが、同様にimage_outputがありません
print(gpt4o.can_be_replaced_by(gemini))  # False

# visionとfunction_callingのみが必要な場合、gemini-3.5-flashはgpt-4oを代替できます
print(gpt4o.can_be_replaced_by(gemini, required_features=["vision", "function_calling"]))  # True
```

### モダリティとマルチモーダルの確認

特定の入力/出力モダリティや、一般的なマルチモーダルサポートを確認できます。

```python
gemini = llmcapa.get("gemini-3.5-flash")

print(gemini.supports("multimodal"))    # True (複数のモダリティをサポート)
print(gemini.supports("audio_input"))   # True
print(gemini.supports("image_output"))  # False
```

### 推論（Reasoning）と思考（Thinking）の確認

OpenAIスタイルの `reasoning_effort` と Anthropicスタイルの `thinking_budget` を区別して確認できます。

```python
o1 = llmcapa.get("o1")
print(o1.supports("reasoning_effort"))  # True
print(o1.supports("thinking_budget"))   # False

claude = llmcapa.get("claude-3-7-sonnet")
print(claude.supports("reasoning_effort"))  # False
print(claude.supports("thinking_budget"))   # True
```

### モデルの一覧表示と検索

```python
# 特定のプロバイダーの全モデルを一覧表示
for c in llmcapa.list_models(provider="anthropic"):
    print(c.model_id, c.context_window)

# 機能条件を指定してモデルを検索
big_reasoning_models = llmcapa.find(
    supports_reasoning=True,
    min_context_window=200000
)
```

### 動的なOpenRouter連携

OpenRouter APIから300以上のモデルを動的に取得・登録し、リアルタイムの機能や価格情報を取得できます。`fetch_openrouter()` を使用して動的にモデルを取得できます。レスポンスはローカルの `~/.llmcapa/openrouter_cache.json` にキャッシュされ、次回以降のインポート時に自動的にロードされるため、最新の更新を反映したオフライン利用が可能です。

```python
# OpenRouterモデルを動的に取得して登録
count = llmcapa.fetch_openrouter()
print(f"OpenRouterから {count} 個のモデルを登録しました！")

# OpenRouterのモデルIDを使用して検索
cap = llmcapa.get("meta-llama/llama-3.3-70b-instruct")
print(cap.context_window)  # 131072
print(cap.pricing)         # {'input_per_1m': 0.1, 'output_per_1m': 0.32, 'currency': 'USD'}
```

### カスタムローカルデータ

ローカルのJSONファイルから独自のモデル定義をロードできます。

```python
llmcapa.load_extra("my_models.json")
```

`my_models.json` のフォーマット:
```json
{
  "models": [
    {
      "provider": "local",
      "model_id": "my-custom-model",
      "context_window": 32768,
      "max_output_tokens": 4096,
      "supports_function_calling": true,
      "aliases": ["my-model-latest"]
    }
  ]
}
```

## 開発

ライブラリの拡張方法、新しいプロバイダーの追加、新しい機能フラグの実装などの詳細については、[DEVELOP.ja.md](DEVELOP.ja.md) ガイドを参照してください。

## CLI

```bash
# 特定のモデルの機能を表示
llmcapa show gpt-4o
llmcapa show gpt-4o --json

# 既知のすべてのモデルを一覧表示
llmcapa list
llmcapa list --provider google
llmcapa list --json --no-deprecated

# 既知のすべてのプロバイダーを一覧表示
llmcapa providers

# 明示的にOpenRouterモデルのキャッシュを取得・更新（キャッシュを強制リフレッシュ）
llmcapa update
```

## 注意事項

- **静的スナップショット**: 同梱されている機能データは静的なスナップショットです。最新のモデル（GPT-5.5、Claude Fable、Gemini 3.5、DeepSeek V4など）を反映するよう努めていますが、プロバイダーは制限や価格を頻繁に変更します。絶対的な正確性が重要な場合は、`fetch_openrouter()` を使用するか、公式ドキュメントを確認してください。

## ライセンス

Apache License 2.0
