# llmcapa

さまざまなLLMモデルの機能（コンテキストウィンドウ、モダリティ、サポートされている機能など）を検索するためのライブラリです。デフォルトで完全にオフラインで動作します。

## 特徴

- **包括的な同梱データ**: OpenAI、Anthropic、Google (Gemini)、Microsoft (Phi)、Amazon (Nova/Titan)、Meta (Llama)、Mistral、Qwen、DeepSeek、xAI (Grok)、NVIDIA、MoonshotAI (Kimi)、zhipu-ai (GLM)、Sakana AI (Fugu)、**Azure AI Foundry**、Novita AI、OpenRouter、**HuggingFace（人気モデル 2,675）**、および日本の国内モデル（デジタル庁の「GENNAI」プラットフォームで採用されているNTT tsuzumi、PFN PLaMo、ELYZA、SoftBank、NEC、Fujitsuなど）のオフライン機能データを同梱しています。
- **実行時依存関係ゼロ**: Python標準ライブラリのみで動作します。外部パッケージ（`pytest` や `build` など）は開発・テスト用のみです。
- **エイリアス解決**: モデルのエイリアスやプロバイダー固有の名前を自動的に解決します（例: `gpt-4o-2024-08-06` -> `gpt-4o`、`gemini-1.5-pro-preview-0409` -> `gemini-1.5-pro`）。
- **プロバイダーエイリアス**: プロバイダー引数は一般的な別名と正規化形式を受け付けます（例: `grok`/`x-ai` → `xai`、`bedrock` → `amazon`、`vertexai`/`gemini` → `google`、`azure` → `azure-openai`、`hf` → `huggingface`、`alibaba`/`dashscope` → `qwen`、`lm-studio` → `lmstudio`）。区切り文字 `_. ` は `-` として扱われます。
- **高度な機能クエリ**: `vision`、`multimodal`、`chat_completion`、`responses_api`、`reasoning_effort`、`thinking_budget`、および特定の入力/出力モダリティ（例: `image_input`、`image_output`、`audio_input`）のサポート状況を確認できます。
- **高いパフォーマンス**: 評価された機能チェックは、冗長な計算を避けるためにメモ化（内部キャッシュ）されます。
- **コスト見積もり**: 入力および出力トークン数に基づいてAPIコストを見積もります。
- **代替モデルチェッカー**: コンテキストウィンドウと必要な機能に基づいて、あるモデルを別のモデルで安全に代替できるかどうかを確認します。
- **トークナイザーマッピング**: モデルの機能から直接トークナイザー名（例: `o200k_base`）にアクセスできます。
- **拡張性**: 独自のローカルJSONモデル定義をロードできます。
- **Ollama & HuggingFace サポート**: **1,638のOllamaモデル**および**2,675の人気HuggingFaceモデル**（236ベースモデル×全サイズバリアント）の機能データを収録。codegemma、llama、qwen、mistral、deepseek、gemma、phi など、ローカル推論向けモデルをカバーしています。
- **FIM（Fill-in-the-Middle）サポート**: `cap.supports('fim')` でコード補完（FIM）対応を確認可能。codegemma、codellama、starcoder2、deepseek-coder、qwen2.5-coder などに対応。
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
# プロバイダーエイリアス: grok→xai, bedrock→amazon, alibaba→qwen, lm-studio→lmstudio, ...
# cap = llmcapa.get("grok-4", provider="grok")
print(cap.context_window)       # 128000
print(cap.max_output_tokens)    # 16384
print(cap.tokenizer_name)       # "o200k_base"

# 機能のサポート状況を確認（文字列またはFeature Enumを使用可能）
from llmcapa import Feature, ReasoningEffort

print(cap.supports(Feature.LLMC_FEAT_VISION))             # True
print(cap.supports(Feature.LLMC_FEAT_RESPONSES_API))      # True
print(cap.supports(Feature.LLMC_FEAT_REASONING_EFFORT))   # False

# reasoning_effortをサポートするモデル向けのReasoningEffort Enum
print(ReasoningEffort.LLMC_EFFORT_HIGH)                   # "high"
# サポートされているすべての機能を一覧表示
print(cap.features())
# ['chat_completion', 'file', 'file_input', 'function_calling', 'image', 'image_input', 'json_mode', 'multimodal', 'responses_api', 'streaming', 'text', 'text_input', 'text_output', 'vision']
```

### トークン数とコストの見積もり

指定されたテキストのトークン数（30以上の主要言語に対応）を簡易的に推定し、APIコストを計算します。

> [!NOTE]
> トークン数の算出はあくまでオフラインでの簡易推定（目安）です。正確なトークン数が必要な場合は、各プロバイダーの公式APIや専用トークナイザーを使用してください。

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

# gpt-4o-miniは同じコンテキストウィンドウを持ち、同じ機能をすべてサポートしています
print(gpt4o.can_be_replaced_by(gpt4o_mini))  # True

# gemini-3.5-flashはより大きなコンテキストウィンドウを持ちますが、responses_api（gpt-4oがサポート）がありません
print(gpt4o.can_be_replaced_by(gemini))  # False

# visionとfunction_callingのみが必要な場合、gemini-3.5-flashはgpt-4oを代替できます
print(gpt4o.can_be_replaced_by(gemini, required_features=["vision", "function_calling"]))  # True
```

### モダリティとマルチモーダルの確認

`Feature` Enum を使用して、特定の入力/出力モダリティや、一般的なマルチモーダルサポートを確認できます。

```python
from llmcapa import Feature

gemini = llmcapa.get("gemini-3.5-flash")

print(gemini.supports(Feature.LLMC_FEAT_MULTIMODAL))    # True (複数のモダリティをサポート)
print(gemini.supports(Feature.LLMC_FEAT_AUDIO_INPUT))   # True
print(gemini.supports(Feature.LLMC_FEAT_IMAGE_OUTPUT))  # False
```

### 推論（Reasoning）と思考（Thinking）の確認

`Feature` Enum を使用して、OpenAIスタイルの `reasoning_effort` と Anthropicスタイルの `thinking_budget` を区別して確認できます。

```python
from llmcapa import Feature

o1 = llmcapa.get("o1")
print(o1.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # True
print(o1.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # False

claude = llmcapa.get("claude-3-7-sonnet")
print(claude.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # False
print(claude.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # True
```



### 推論努力（Reasoning Effort）の値

特定モデルがサポートする有効な `reasoning_effort` 値の一覧を取得します:

```python
cap = llmcapa.get("gpt-5.5")
print(cap.get_reasoning_effort_values())
# ['none', 'minimal', 'low', 'medium', 'high', 'xhigh']

cap2 = llmcapa.get("o1")
print(cap2.get_reasoning_effort_values())
# ['none', 'low', 'medium', 'high']

# reasoning_effort 非対応モデルは空リストを返す
cap3 = llmcapa.get("gpt-4o")
print(cap3.get_reasoning_effort_values())
# []
```

### 思考バジェット（Thinking Budget）の値

`thinking_budget` をサポートするモデルについて、有効な値の情報を取得します:

```python
cap = llmcapa.get("claude-sonnet-4-20250501")
print(cap.get_thinking_budget_values())
# {'type': 'token_range', 'min': 1024, 'max': 128000}

cap2 = llmcapa.get("deepseek-r1")
print(cap2.get_thinking_budget_values())
# {'type': 'token_range', 'min': 1024, 'max': 8192}

# thinking_budget 非対応モデルは空 dict を返す
cap3 = llmcapa.get("gpt-4o")
print(cap3.get_thinking_budget_values())
# {}
```

### Sakana Fugu（マルチエージェント・オーケストレーション）

Sakana AI の Fugu は、単一モデルとして提示されるマルチエージェント・オーケストレーションシステムです。フロンティアモデルを動的に協調させ、複雑なタスクに取り組みます。llmcapa は Fugu と Fugu Ultra の両方の機能データを同梱しています。

```python
import llmcapa

# Fugu モデルの検索（大文字小文字非区別、エイリアス解決）
fugu = llmcapa.get("fugu")
print(fugu.context_window)       # 272000
print(fugu.max_output_tokens)    # 128000
print(fugu.supports("vision"))   # True（text+image 入力）
print(fugu.pricing)              # {'input_per_1m': 5.0, 'output_per_1m': 30.0, ...}

fugu_ultra = llmcapa.get("fugu-ultra")
print(fugu_ultra.context_window) # 1000000（1M トークン）
print(fugu_ultra.pricing)        # {'input_per_1m': 5.0, 'output_per_1m': 30.0, ...}

# Sakana モデル一覧
for cap in llmcapa.list_models(provider="sakana"):
    print(cap.model_id, cap.context_window)
```

### FIM（Fill-in-the-Middle）サポート

モデルがコード補完（FIM）に対応しているか確認できます：

```python
import llmcapa

cap = llmcapa.get("codegemma:2b", provider="ollama")
print(cap.supports("fim"))       # True
print(cap.supports("vision"))    # False
print("fim" in cap.features())   # True

cap2 = llmcapa.get("llama3.1", provider="ollama")
print(cap2.supports("fim"))      # False
```

`Feature` 列挙型でも利用可能です：

```python
from llmcapa import Feature
cap = llmcapa.get("starcoder2", provider="ollama")
print(cap.supports(Feature.LLMC_FEAT_FIM))  # True
```

### モデルの一覧表示と検索

```python
# 特定のプロバイダーの全モデルを一覧表示
for c in llmcapa.list_models(provider="anthropic"):
    print(c.model_id, c.context_window)

# プレフィックス検索（provider は任意。エイリアス可）
search_results = llmcapa.search("codegemma", provider="ollama")
search_results = llmcapa.search("gpt-4o")  # 全プロバイダー
big_reasoning_models = llmcapa.find(
    supports_reasoning=True,
    min_context_window=200000
)
```

### オンデマンドでのOpenRouter連携（キャッシュ更新）

最新のモデルデータや価格情報を取得したい場合は、必要に応じて（オンデマンドで）OpenRouter APIからモデルデータを取得し、ローカルに登録できます。`fetch_openrouter()` を実行すると、データは `~/.llmcapa/openrouter_cache.json` にキャッシュされ、次回以降のインポート時に自動的にロードされます。これにより、通常の利用時は完全にオフラインのまま最新データを活用できます。

```python
# OpenRouterモデルを動的に取得して登録
count = llmcapa.fetch_openrouter()
print(f"OpenRouterから {count} 個のモデルを登録しました！")

# OpenRouterのモデルIDを使用して検索
cap = llmcapa.get("meta-llama/llama-3.3-70b-instruct")
print(cap.context_window)  # 131072
print(cap.pricing)         # {'input_per_1m': 0.1, 'output_per_1m': 0.32, 'currency': 'USD'}
```


### Novita AI（同梱プロバイダー）

Novita AI は、200以上のオープンソース／独自モデルを単一 API で提供するクラウドプラットフォームです。llmcapa は DeepSeek、Qwen、Meta Llama、GLM、Gemini などを含む 136 の Novita AI モデルの機能データ（Novita 固有の価格設定付き）を同梱しています。

`provider="novita"` で Novita AI モデルにスコープを絞れます:

```python
import llmcapa

# provider スコープで Novita AI モデルを検索
cap = llmcapa.get("deepseek/deepseek-v3.2", provider="novita")
print(cap.context_window)  # 163840
print(cap.pricing)         # {'input_per_1m': 0.0269, 'output_per_1m': 0.04, 'currency': 'USD'}

cap = llmcapa.get("qwen/qwen3.7-max", provider="novita")
print(cap.context_window)  # 1000000

# Novita AI モデル一覧
for c in llmcapa.list_models(provider="novita"):
    print(c.model_id, c.context_window, c.pricing)

# Novita を含む全プロバイダー
print(llmcapa.providers())
# ['...', 'novita', '...']
```

### オンデマンドでの HuggingFace 連携（キャッシュ更新）

`fetch_huggingface()` を使うと、HuggingFace API から人気モデルをオンデマンドで取得・登録できます。ダウンロード数の多い text-generation / image-text-to-text モデルを取得し、基本的な機能を登録して `~/.llmcapa/huggingface_cache.json` にローカルキャッシュします。

```python
# 上位 100 の HuggingFace モデルを動的に取得・登録
count = llmcapa.fetch_huggingface()
print(f"Registered {count} models from HuggingFace!")

# HuggingFace モデル ID で検索
cap = llmcapa.get("deepseek-ai/DeepSeek-V4-Flash")
print(cap.context_window)   # 4096（推定。HF API では正確な値が取れない場合あり）
print(cap.supports_vision)  # False（text-generation パイプライン）

# 取得件数を変更
count = llmcapa.fetch_huggingface(limit=200)
```

> **Note**: HuggingFace の一覧 API はコンテキストウィンドウ、価格、詳細な機能データを提供しません。登録されるモデルのコンテキストウィンドウはモデルファミリーに基づく推定値です（例: Llama 3: 8K、Qwen3: 128K）。同梱の `huggingface.json` には、改善されたコンテキスト推定付きの人気 text-generation モデル 2,675 件が含まれます。正確な仕様が必要な場合は、各モデルの公式ドキュメントを参照してください。

### トークン数のカウント（スタンドアロン）

指定されたモデルに最適なトークナイザーを使用して、単一テキストまたはチャットメッセージのトークン数をカウントします。

```python
# テキストのトークン数をカウント
import llmcapa
tokens = llmcapa.count_tokens("Hello, world!", "gpt-4o")
print(tokens)  # tiktokenがインストールされていれば正確な値、それ以外は推定値

# チャットメッセージのトークン数（オーバーヘッド含む）
messages = [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi there!"},
]
total = llmcapa.count_messages_tokens(messages, "gpt-4o")
print(total)
```

### プログラムによるモデル登録

JSONファイルを使わずに直接Capabilityを登録:

```python
from llmcapa import Capability

cap = Capability(
    provider="local",
    model_id="my-model",
    context_window=4096,
    max_output_tokens=1024,
    supports_function_calling=True,
    aliases=["mm"],
)
llmcapa.register(cap)

print(llmcapa.get("my-model").context_window)  # 4096
```

> **注意**: `llmcapa.get()` はモデルが見つからない場合 `ModelNotFoundError` を送出します。

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

# テキストやメッセージのトークン数をカウント
llmcapa tokens gpt-4o "Hello, world!"
llmcapa tokens gpt-4o --messages '[{"role":"user","content":"Hi"}]'

# 起動時にローカルJSONファイルから追加モデルをロード
llmcapa --extra my_models.json show gpt-4o

# 明示的にOpenRouterモデルのキャッシュを取得・更新（キャッシュを強制リフレッシュ）
llmcapa update
```

## 注意事項

- **静的スナップショット**: 同梱されている機能データは静的なスナップショットです。最新のモデル（GPT-5.5、Claude Fable、Gemini 3.5、DeepSeek V4など）を反映するよう努めていますが、プロバイダーは制限や価格を頻繁に変更します。絶対的な正確性が重要な場合は、`fetch_openrouter()` を使用するか、公式ドキュメントを確認してください。

## ライセンス

Apache License 2.0
