# llmcapa

さまざまなLLMモデルの機能（コンテキストウィンドウ、モダリティ、サポートされている機能など）を検索するためのライブラリです。デフォルトで完全にオフラインで動作します。

## 特徴

- **包括的な同梱データ**: OpenAI、Anthropic、Google (Gemini)、Microsoft (Phi)、Amazon (Nova/Titan)、Meta (Llama)、Mistral、Qwen、DeepSeek、xAI (Grok)、NVIDIA、MoonshotAI (Kimi)、zhipu-ai (GLM)、Sakana AI (Fugu)、**Azure AI Foundry**、Novita AI、**Together AI（98モデル）**、OpenRouter、**HuggingFace（人気モデル 2,904）**、**Modellix LLM・メディアモデル**（LLM 29件、メディア178件）、**TypeSafe（Jev / System One の決定出力モデル）**、および日本の国内モデル（デジタル庁の「GENNAI」プラットフォームで採用されているNTT tsuzumi、PFN PLaMo、ELYZA、SoftBank、NEC、Fujitsuなど）のオフライン機能データを同梱しています。
- **実行時依存関係ゼロ**: Python標準ライブラリのみで動作します。外部パッケージ（`pytest` や `build` など）は開発・テスト用のみです。
- **エイリアス解決**: モデルのエイリアスやプロバイダー固有の名前を自動的に解決します（例: `gpt-4o-2024-08-06` -> `gpt-4o`、`gemini-1.5-pro-preview-0409` -> `gemini-1.5-pro`）。
- **プロバイダーエイリアス**: プロバイダー引数は一般的な別名と正規化形式を受け付けます（例: `grok`/`x-ai` → `xai`、`bedrock`/`aws-bedrock`/`aws` → `amazon`、`vertexai` → `vertex-ai`、`open-ai` → `openai`、`google-ai` → `google`、`azure` → `azure-openai`、`hf` → `huggingface`、`alibaba`/`dashscope` → `qwen`、`lm-studio` → `lmstudio`、`modellix-ai` → `modellix`）。区切り文字 `_. ` は `-` として扱われます。
- **高度な機能クエリ**: `vision`、`multimodal`、`chat_completion`、`responses_api`、`realtime`、`tool_search`、`reasoning_effort`、`reasoning_mode`、`thinking_budget`、および特定の入力/出力モダリティ（例: `image_input`、`audio_input`、`file_input`、`speech_input`、`embedding_output`）のサポート状況を確認できます。PDFは`file_input`のサブタイプとして扱われます。
- **高いパフォーマンス**: 評価された機能チェックは、冗長な計算を避けるためにメモ化（内部キャッシュ）されます。
- **コスト見積もり**: 入力および出力トークン数に基づいてAPIコストを見積もります。
- **代替モデルチェッカー**: コンテキストウィンドウと必要な機能に基づいて、あるモデルを別のモデルで安全に代替できるかどうかを確認します。
- **トークナイザーマッピング**: モデルの機能から直接トークナイザー名（例: `o200k_base`）にアクセスできます。
- **拡張性**: 独自のローカルJSONモデル定義をロードできます。
- **Ollama & HuggingFace サポート**: **1,656のOllamaモデル**および**2,904の人気HuggingFaceモデル**（236ベースモデル×全サイズバリアント）の機能データを収録。codegemma、llama、qwen、mistral、deepseek、gemma、phi など、ローカル推論向けモデルをカバーしています。
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

### Realtimeと追加モダリティの確認

`Feature` EnumでRealtime API、ファイル、音声（Speech）、埋め込み出力を確認できます。PDFはファイル入力のサブタイプです。

```python
from llmcapa import Feature

realtime = llmcapa.get("gpt-realtime-2")
print(realtime.supports(Feature.LLMC_FEAT_REALTIME))       # True
speech = llmcapa.get("nova-2-sonic-v1", provider="amazon")
print(speech.supports(Feature.LLMC_FEAT_SPEECH_INPUT))     # True
print(speech.supports(Feature.LLMC_FEAT_SPEECH_OUTPUT))    # True

pdf_model = llmcapa.get("muse-spark-1.1", provider="meta")
print(pdf_model.supports(Feature.LLMC_FEAT_FILE_INPUT))    # True

embedding = llmcapa.get("gemini-embedding-001", provider="google")
print(embedding.supports(Feature.LLMC_FEAT_EMBEDDING_OUTPUT)) # True
```

`bedrock`はAmazonへ解決されます。`google`と`vertex-ai`は別プロバイダーです。

```python
nova = llmcapa.get("nova-sonic-v1", provider="bedrock")
gemini_live = llmcapa.get("gemini-3.1-flash-live-preview", provider="google")
```

### 音声入力・出力の詳細メタデータ

音声モダリティを持つモデルには、`cap.audio` として音声処理の詳細が収録されます。公式ドキュメントにない値は推測せず、`status="inferred"` としてモダリティ由来の基本情報のみを保持します。

```python
cap = llmcapa.get("gpt-4o-transcribe", provider="openai")
print(cap.audio.transcription)          # True
print(cap.audio.input_formats)          # ('flac', 'mp3', ...)
print(cap.audio.max_input_bytes)        # 25000000

voice = llmcapa.get("gpt-4o-mini-tts", provider="openai")
print(voice.audio.speech_generation)    # True
print(voice.audio.output_formats)       # ('mp3', 'opus', ...)
print(voice.audio.voice_values)          # 音声ID一覧
print(voice.audio.speed_min)             # 0.25
print(voice.audio.speed_max)             # 4.0
```

`AudioCapability` には、文字起こし、翻訳、話者分離、タイムスタンプ、対応形式、MIMEタイプ、サンプルレート、音声合成の声・速度・出力形式、ストリーミング／Realtime API対応、公式ソースURLなどが含まれます。

### 動画入力・出力の詳細メタデータ

動画モダリティを持つモデルには、`cap.video` として生成・理解・編集の詳細が収録されます。

```python
video = llmcapa.get("sora-2", provider="openai")
print(video.video.generation)           # True
print(video.video.text_to_video)        # True
print(video.video.output_formats)       # ('mp4',)

reel = llmcapa.get("nova-reel-v1", provider="amazon")
print(reel.video.image_to_video)        # True
print(reel.video.duration_values_seconds)  # (6.0,)
print(reel.video.output_mime_types)     # ('video/mp4',)
```

`VideoCapability` には、Text-to-Video、Image-to-Video、Video-to-Video、動画理解、編集、補間、延長、アップスケール、リップシンク、入力形式、解像度、FPS、フレーム数、動画長、音声トラック、出力コーデック、ストリーミング／Realtime対応などが含まれます。

### ドキュメント・Embedding・Rerank・空間データ

次の特殊な入出力も専用メタデータへ正規化しています。

```python
doc = llmcapa.get("gemini-embedding-001", provider="google")
print(doc.embedding.dimensions)       # プロバイダーのメタデータ（収録時に利用可能な場合）
print(doc.embedding.max_input_tokens) # プロバイダーのメタデータ（収録時に利用可能な場合）

rerank = llmcapa.get("rerank-v3.5", provider="cohere")
print(rerank.rerank.rerank)            # True

# file/pdf/json/csv/code 入力を持つモデル
print(cap.document.input_formats)

# geospatial / 3d-image モデル
print(cap.spatial.kind_values)
```

`document`、`embedding`、`rerank`、`spatial`、`decision` も、既存の位置引数互換性を壊さないよう `Capability` の末尾に追加されています。

### 決定出力（Decision / System One）

文章を生成せず、型付きの決定と較正済み確率だけを返すモデル（TypeSafe の Jev など、System One 系）は、出力モダリティを `decision` として表現します。`text_output` は false、`chat_completion` は false、`multimodal` も成立しません（入力は text のみ）。

```python
import llmcapa

jev = llmcapa.get("jev-1.13.0", provider="typesafe")
print(jev.input_modalities)                    # ['text']
print(jev.output_modalities)                   # ['decision']
print(jev.supports("decision_output"))         # True
print(jev.supports("text_output"))             # False
print(jev.supports("chat_completion"))         # False

print(jev.decision.question_kinds)             # ('choice', 'score', 'noul')
print(jev.decision.answer_fields)              # ('choice', 'score', 'noul', 'probabilities', 'confidence')
print(jev.decision.returns_confidence)         # True
print(jev.decision.calibrated_confidence)      # True
print(jev.decision.free_form_text)             # False
print(jev.decision.type_errors_possible)       # False
print(jev.decision.max_total_tokens)           # 64000
print(jev.decision.endpoints)                  # ('https://api.typesafe.ai/v1/systemone',)
```

OpenRouter 経由のルートは `/api/v1` ではなく Alpha の Decisions エンドポイントを使い、OpenAI 互換の Responses API ではありません。

```python
route = llmcapa.get("typesafe/jev-1.13", provider="openrouter")
print(route.supports("decision_output"))  # True
print(route.supports("responses_api"))    # False
print(route.decision.endpoints)           # ('https://openrouter.ai/api/alpha/decisions',)
```

決定出力は独立した出力モダリティとして扱われるため、`can_be_replaced_by()` は決定モデルをテキスト生成モデルで代替可能とは判定しません。

### 推論（Reasoning）と思考（Thinking）の確認

プロバイダー共通APIの仕様は [docs/API_SPECIFICATION.md](docs/API_SPECIFICATION.md) を参照してください。

`Feature` Enum を使用して、OpenAIスタイルの `reasoning_effort` と Anthropicスタイルの `thinking_budget` を区別して確認できます。

```python
from llmcapa import Feature

o1 = llmcapa.get("o1")
print(o1.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # True
print(o1.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # False

claude = llmcapa.get("claude-sonnet-4-5", provider="anthropic")
print(claude.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # False
print(claude.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # True
```

Google GeminiのネイティブAPIは、OpenAIの `reasoning_effort` ではなく、
Google固有の思考制御を使用します。`provider="google"` はGoogle
Generative Language APIの経路を表します。

```python
gemini25 = llmcapa.get("gemini-2.5-flash", provider="google")
print(gemini25.supports(Feature.LLMC_FEAT_REASONING_EFFORT))  # False
print(gemini25.supports(Feature.LLMC_FEAT_THINKING_BUDGET))   # True

gemini3 = llmcapa.get("gemini-3-flash-preview", provider="google")
print(gemini3.supports(Feature.LLMC_FEAT_REASONING_EFFORT))   # False
print(gemini3.supports(Feature.LLMC_FEAT_THINKING_LEVEL))    # True
```

Gemini 2.5は `thinking_budget`、Gemini 3以降は `thinking_level` を使用します。
`google` と `vertex-ai` は別のプロバイダー経路であり、ネイティブGoogle
カタログをOpenAI互換APIとして扱いません。

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

### Tool Search と Reasoning Mode

`tool_search` は Responses API の公式ツール一覧をモデルごとに記録します。`None` は対応可否が未確認であることを示します。Reasoning mode は reasoning effort とは独立した設定です。

```python
nano = llmcapa.get("gpt-5.4-nano", provider="openai")
print(nano.supports("tool_search"))  # False

luna = llmcapa.get("gpt-6-luna", provider="openai")
print(luna.supports("tool_search"))  # True

cap = llmcapa.get("gpt-5.6")
print(cap.get_reasoning_mode_values())  # ['standard', 'pro']
```

GPT-5.6 と GPT-6 の Responses API モデルでは、`reasoning.mode` に `standard` または `pro` を指定できます。`reasoning.effort` は別の設定です。

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

### Thinking Level の値

Gemini 3 などの離散的な思考制御を持つAPIは、`reasoning_effort` や数値の `thinking_budget` とは別に `thinking_level` を使用します。

```python
cap = llmcapa.get("gemini-3-flash-preview", provider="vertex-ai")
print(cap.supports(Feature.LLMC_FEAT_THINKING_LEVEL))  # True
print(cap.get_thinking_level_values())
# ['minimal', 'low', 'medium', 'high']

budget = llmcapa.get("gemini-2.5-flash", provider="vertex-ai")
print(budget.get_thinking_budget_values())
# {'type': 'token_range', 'min': 0, 'max': 24576}
```

`llmcapa` はプロバイダー固有の機能メタデータを提供します。実際の `thinking_level` や `thinking_budget` の値は、アプリケーションからプロバイダーAPIへ渡してください。

プロバイダーを意識しないリクエスト構築には `thinking_control` を使用できます。

```python
control = cap.get_thinking_control()
# {'kind': 'level', 'parameter': 'thinking_level',
#  'values': ['minimal', 'low', 'medium', 'high']}

minimax = llmcapa.get("MiniMax-M3", provider="minimax")
print(minimax.get_thinking_control())
# {'kind': 'toggle', 'parameter': 'thinking',
#  'values': ['enabled', 'disabled'], ...}
```

これは後方互換の追加機能で、既存の `reasoning_effort` や `thinking_budget` のAPIは変更しません。

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

> **Note**: OpenRouterのResponses API（`POST /api/v1/responses`）はOpenAI互換のゲートウェイ機能で、モデル固有ではなくOpenRouterの全ルートで利用できます。したがって`provider="openrouter"`のすべてのモデルは`responses_api`をサポートします。ただし**ステートレスのみ**で、`store: true`と`previous_response_id`は400エラーで拒否されます。会話履歴は毎回リクエストに含める必要があります。ネイティブプロバイダー経路（`provider="openai"`など）の`responses_api`は各プロバイダーの実装状況を表し、OpenRouterのゲートウェイ機能とは別に管理されます。

### Novita AI（同梱プロバイダー）

Novita AI は、200以上のオープンソース／独自モデルを単一 API で提供するクラウドプラットフォームです。llmcapa は DeepSeek、Qwen、Meta Llama、GLM、Gemini などを含む 157 の Novita AI モデルの機能データ（Novita 固有の価格設定付き）を同梱しています。

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

> **Note**: HuggingFace の一覧 API はコンテキストウィンドウ、価格、詳細な機能データを提供しません。登録されるモデルのコンテキストウィンドウはモデルファミリーに基づく推定値です（例: Llama 3: 8K、Qwen3: 128K）。同梱の `huggingface.json` には、改善されたコンテキスト推定付きの人気 text-generation モデル 2,904 件が含まれます。正確な仕様が必要な場合は、各モデルの公式ドキュメントを参照してください。

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

## Computer Use / CUA capability

`llmcapa` は、モデルが Computer Use（CUA）に対応しているかをメタデータとして確認できます。Computer Useの操作自体は実行しません。`computer_use` はオプション項目なので、既存のモデル定義や利用コードとの互換性を維持できます。

```python
import llmcapa

cap = llmcapa.get("gemini-3-flash-preview", provider="google")
computer = cap.computer_use

if computer and computer.supported:
    print(computer.native)
    print(computer.tool_type)
    print(computer.tool_version)
    print(computer.beta_header)
    print(sorted(computer.actions))
```

簡易判定用のAPIも利用できます。

```python
llmcapa.supports_computer_use("gemini-3-flash-preview", provider="google")
llmcapa.supports_computer_action("gemini-3-flash-preview", "click", provider="google")
llmcapa.supports_computer_environment("gemini-3-flash-preview", "desktop", provider="google")
```

### ネイティブ対応とカスタムハーネス対応

- `native=True`: プロバイダーがネイティブComputer Tool/APIを提供する場合。例えばAnthropicでは、対応モデルに `computer_20251124` または `computer_20250124` と対応するベータヘッダーを使用します。
- `native=False`: 外部のComputer Runtimeや独自ツールハーネスを組み合わせて利用できる場合。プロバイダーのネイティブComputer Toolを、その接続経路が提供していることを意味しません。QwenのVisual Agent、ローカルモデル、OpenRouter経由のカスタムツール利用などが該当します。

`tool_version` は正規化したComputer Toolバージョン、`tool_type` はプロバイダー/APIに渡す値、`beta_header` は必要なリクエストヘッダーまたはリクエスト項目です。`checked_at` には対応情報を確認した日付を記録します。モデルのバージョンとComputer Toolのバージョンは分けて管理します。

`llmcapa` は対応状況のメタデータだけを提供します。スクリーンショット取得、マウス・キーボード操作、エージェントループ、サンドボックス化、高リスク操作のユーザー確認はアプリケーション側の責任です。

### 登録済み経路の例

```python
# Google Gemini APIへ直接接続
google = llmcapa.get("gemini-3-flash-preview", provider="google")
assert google.computer_use.tool_type == "computer_use"

# Qwen visual agent with a custom harness
qwen = llmcapa.get("qwen3-vl-235b-a22b-instruct", provider="qwen")
assert qwen.computer_use.native is False

# OpenAI Responses API
openai = llmcapa.get("computer-use-preview", provider="openai")
assert openai.computer_use.tool_type == "computer_use_preview"
```

OpenRouterなどのゲートウェイは、直接のプロバイダー経路とは分けて管理します。汎用Tool Callingとカスタムハーネスを組み合わせることはできますが、プロバイダーのネイティブComputer Toolと自動的に同一視しません。

### Computer Useの置換判定

モデル置換時にComputer Useの互換性も要求する場合は、明示的に指定します。置換判定では、単なる `supports("computer_use")` の真偽値ではなく、プロバイダー/API固有のtool type（schema）、対応環境、アクションを比較します。tool versionはメタデータとして扱い、互換性の判定条件にはしません。`required_actions` は現在Computer Use専用です。

```python
source.can_be_replaced_by(
    target,
    required_features=["vision"],
    required_actions=["screenshot", "left_click", "type"],
    required_environment="desktop",
)
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
llmcapa list --provider anthropic --wide

# プレフィックスでモデルを検索
llmcapa search claude --limit 10
llmcapa search gpt --provider azure --format json

# 列・並び順・出力形式を指定
llmcapa search claude --columns provider,model_id,ctx,out,flags,price
llmcapa search claude --sort=-ctx --limit 5
llmcapa search claude --format csv        # または md / json

# 機能フラグ・サイズでモデルを検索（decision モデルなど）
llmcapa find decision=true
llmcapa find embedding=true --provider amazon
llmcapa find vision=false --min-context 64000

# 既知のすべてのプロバイダーを一覧表示
llmcapa providers

# テキストやメッセージのトークン数をカウント
llmcapa tokens gpt-4o "Hello, world!"
llmcapa tokens gpt-4o --messages '[{"role":"user","content":"Hi"}]'

# 起動時にローカルJSONファイルから追加モデルをロード
llmcapa --extra my_models.json show gpt-4o

# OpenRouterのキャッシュだけを明示的に取得・更新
llmcapa update

# 開発用: OpenAI公式カタログを動的に再取得
python scripts/_update_all_providers.py --provider openai
```

## 注意事項

- **静的スナップショット**: 同梱されている機能データは静的なスナップショットです。最新のモデル（GPT-5.5、Claude Fable、Gemini 3.5、DeepSeek V4など）を反映するよう努めていますが、プロバイダーは制限や価格を頻繁に変更します。絶対的な正確性が重要な場合は、`fetch_openrouter()` を使用するか、公式ドキュメントを確認してください。

## ライセンス

Apache License 2.0
