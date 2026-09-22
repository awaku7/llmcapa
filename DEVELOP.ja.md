# 開発者ガイド

このドキュメントでは、`llmcapa` ライブラリの開発、拡張、およびメンテナンス方法について説明します。

---

## プロジェクト構成

```
llmcapa/
├── pyproject.toml          # ビルド設定 (Hatchling / PEP 621)
├── LICENSE                 # Apache License 2.0
├── README.md               # ユーザー向けドキュメント（英語）
├── README.ja.md            # ユーザー向けドキュメント（日本語）
├── DEVELOP.md              # 開発者ガイド（英語）
├── DEVELOP.ja.md           # 開発者ガイド（日本語）
├── src/llmcapa/
│   ├── __init__.py         # 公開APIのエントリーポイント
│   ├── models.py           # 機能データクラスと機能評価
│   ├── specialized_capabilities.py  # document / embedding / rerank / spatial / decision レコード
│   ├── registry.py         # インメモリレジストリ、ロード、およびOpenRouter/HuggingFace取得
│   ├── cli.py              # コマンドラインインターフェース
│   ├── tokenizer.py        # トークンカウント（オフライン、プロバイダー別）
│   └── data/               # 同梱されているオフライン機能データ (JSON)
│       ├── __init__.py
│       ├── openai.json
│       ├── anthropic.json
│       └── ...             # プロバイダーごとのカタログ（70件超）。集約ファイルを含む
├── scripts/                # プロバイダー別の更新・スクレイプ・後処理スクリプト
│   ├── _update_*.py        # 公式ソースから各プロバイダーを更新
│   ├── _scrape_*.py        # 公式ページのスクレイピング
│   └── _*_postprocess.py   # audio / video / image / structured 補正
├── docs/                   # 仕様・スクレイピングノート
└── tests/                  # ユニットテスト (pytest)
    ├── test_registry.py
    ├── test_cache.py
    ├── test_advanced.py
    ├── test_cli.py
    ├── test_computer_use.py
    ├── test_audio_capability.py
    ├── test_video_capability.py
    ├── test_image_capability.py
    ├── test_decision_capability.py
    └── test_specialized_capability.py
```

---

## 設計思想

1. **オフラインファースト**: すべてのコア機能データは、パッケージ内にJSONファイルとして静的に同梱されています。標準的な検索時にネットワークリクエストは発生しません。
2. **実行時依存関係ゼロ**: ライブラリはPython標準ライブラリのみで動作する必要があります。外部パッケージ（`pytest` や `build` など）は、開発およびテスト専用です。
3. **不変性とパフォーマンス**: `Capability` データクラスは `frozen=True` です。機能チェック時の冗長な計算を避けるため、評価結果はメモ化（内部キャッシュ）されます。

---


---

## プロバイダーエイリアスと正規化

`get()`、`list_models()`、`search()` は、ルックアップ前にプロバイダー名を正規化し、エイリアスを解決します。

### 正規化
1. 小文字化
2. 区切り文字 `_. \t` を `-` に統一（例: `azure_openai` → `azure-openai`、`X AI` → `x-ai`）

### 組み込みエイリアス（`Registry._provider_aliases`）

| 正規プロバイダー名 | 受け付けるエイリアス |
|---|---|
| `deepseek` | `deepseek-ai` |
| `meta` | `meta-llama` |
| `mistral` | `mistralai` |
| `xai` | `x-ai`, `grok` |
| `anthropic` | `claude` |
| `openai` | `open-ai` |
| `google` | `google-ai`, `gemini` |
| `vertex-ai` | `vertexai` |
| `azure-openai` | `azure` |
| `zhipu` | `zai`, `z-ai` |
| `moonshotai` | `moonshot`, `kimi` |
| `amazon` | `bedrock`, `aws-bedrock`, `aws` |
| `xiaomi` | `mimo` |
| `huggingface` | `hf` |
| `qwen` | `alibaba`, `dashscope` |
| `lmstudio` | `lm-studio`, `lm_studio` |
| `together` | `together-ai`, `togethercomputer` |
| `vercel` | `vercel-ai-gateway`, `vercel-gateway`, `ai-gateway` |
| `modellix` | `modellix-ai` |
| `llama-cpp` | `llama`, `llama_cpp` |

例:

```python
import llmcapa

# いずれも同じプロバイダーカタログに解決される
llmcapa.list_models(provider="grok")
llmcapa.list_models(provider="x-ai")
llmcapa.list_models(provider="xai")

llmcapa.get("claude-sonnet-4", provider="claude")   # → anthropic
llmcapa.search("gpt-4o", provider="azure")          # → azure-openai
```

新しいエイリアスを追加する場合は `src/llmcapa/registry.py` の `_provider_aliases` を更新し、`tests/test_registry.py` にテストを追加してください。

### `search(provider=None)`

- `provider` は **任意**（0.4.0 以降）。
- 省略時は flat な `_models` ではなく `list_models` / `_by_provider` 経由で全プロバイダーを走査するため、複数プロバイダーに存在する同一 model id も保持されます。
- 指定時は `list_models` / `get` と同じエイリアス・正規化パスを使います。

`meta/muse-spark-1.3` のようなルート修飾 ID は `openrouter` カタログに属します。ネイティブカタログは集約側のルートプレフィックスをエイリアスとして追加しません。ただしネイティブプロバイダー自身の名前空間にスラッシュを含むことはあります（例: Novita の `baichuan/baichuan-m2-32b`）。OpenRouter のルートを検索する場合は `provider="openrouter"` を指定してください。

## カタログ更新スクリプトの方針

プロバイダーのカタログ更新は、プロバイダーごとの公式ソースを使う個別スクリプトで行います。全プロバイダーをOpenRouterのデータで一括置換するスクリプトは使用しません。

ネイティブプロバイダーのカタログは、レコード取得に OpenRouter を使ってはなりません。OpenRouter API から構築するのは `openrouter.json` だけです（`scripts/_update_openrouter.py`）。他の `scripts/_update_*.py` は公式ドキュメントページまたは公式モデル API を直接解析します。`scripts/openrouter_providers/` 配下のシムは歴史的参照用であり、現役の更新スクリプトから import してはなりません。

### OpenAI

```bash
python scripts/_update_all_providers.py --provider openai
# または
python scripts/_update_openai.py
```

`_update_openai.py` は `https://developers.openai.com/api/docs/models/all.md` から詳細ページを動的に発見し、各ページと公式料金ページを解析します。モデル名やエイリアスをスクリプトへハードコードしません。現在の公式インデックスに存在しない既存レコードは、レガシー互換用としてのみ保持します。

### OpenRouter

```bash
python scripts/update_catalog_from_openrouter.py
```

これは `openrouter.json` **だけ**を更新します。他プロバイダーのJSONをOpenRouterデータで置き換えません。live API から再構築する場合は `scripts/_update_openrouter.py` を使います。

### 全ファイル対象の補正処理

`scripts/_postprocess_catalogs.py` はモデル発見やプロバイダーカタログの一括取得を行いません。既存JSONに対する補正が本体です。具体的には、公式料金メタデータ（`scripts/metadata/anthro_prices.json`、`ds_prices.json`）による Anthropic / DeepSeek の上書き、コード系モデル名パターンによる `supports_fim` の一括修正、`meta-llama` → `meta`・`x-ai` → `xai` のプロバイダー名統合、audio / video / structured / image の正規化（`_audio_capability_postprocess` 等の `apply()` を呼び出し）、および `provider_update_log.md` への追記です。

### 画像 Capability の後処理

`scripts/_image_capability_postprocess.py` は画像生成レコード用の共有後処理です。画像出力を持ち、認識可能な画像生成ファミリーに属するカタログレコードにのみ、保守的な `ImageCapability` メタデータを付与します。画像入力だけでは画像生成とみなしません。未確認の入力形式・MIME・バイト上限・ピクセル上限は推測で補完せず未設定のままにします。

`_update_all_providers.py` はプロバイダー更新の成功後にこのステップを実行します。直接監査する場合は以下を実行します:

```bash
python scripts/_image_capability_postprocess.py
```

監査では、生成メタデータの欠落と、曖昧または画像解析系の出力レコードを区別します。

## 新しいプロバイダーの追加

新しいモデルプロバイダー（例: `cohere`）を追加する場合:

### 1. データファイルの作成
`src/llmcapa/data/<provider_name>.json` に新しいJSONファイルを作成します。

```json
{
  "models": [
    {
      "provider": "cohere",
      "model_id": "command-r-plus",
      "display_name": "Command R+",
      "context_window": 128000,
      "max_output_tokens": 4000,
      "input_modalities": ["text"],
      "output_modalities": ["text"],
      "supports_chat_completion": true,
      "supports_function_calling": true,
      "supports_json_mode": true,
      "supports_streaming": true,
      "supports_vision": false,
      "supports_reasoning": false,
      "tokenizer_name": "cohere-command",
      "pricing": {
        "input_per_1m": 2.5,
        "output_per_1m": 10.0,
        "currency": "USD"
      },
      "knowledge_cutoff": "2024-01",
      "aliases": ["cohere/command-r-plus"]
    }
  ]
}
```

### 2. 動作確認テストの追加
`tests/test_registry.py` に新しいプロバイダーが `providers()` / `list_models()` / `get()` 経由で取得できることを確認するテストを追加します（例: `test_together_provider`、`test_new_providers_registered` を参照）。現在の `test_providers()` は規模だけを検証します:

```python
def test_providers():
    p = llmcapa.providers()
    assert isinstance(p, list)
    assert len(p) > 10
    assert "openai" in p
    assert "novita" in p
```

新しいプロバイダー（例: `cohere` は `src/llmcapa/data/cohere.json` として同梱済み）のように、最低限 `providers()` に含まれることと、代表モデルが `get()` できることを検証してください。

---

## 新しい機能フラグの追加

新しい機能フラグ（例: `supports_structured_outputs`）を追加する場合:

現在の標準 `Feature` Enum（`src/llmcapa/models.py`）には、Realtime と拡張モダリティも含まれます:

- `LLMC_FEAT_REALTIME`
- `LLMC_FEAT_FILE_INPUT`（PDFを含むファイル系入力。PDFは独立した Enum ではなく `file_input` のサブタイプとして評価されます）
- `LLMC_FEAT_SPEECH_INPUT` / `LLMC_FEAT_SPEECH_OUTPUT`
- `LLMC_FEAT_EMBEDDING_OUTPUT`（`embedding` / `embeddings` の表記揺れを吸収）
- `LLMC_FEAT_FIM`、`LLMC_FEAT_MULTIMODAL`、`LLMC_FEAT_THINKING_LEVEL`
- `LLMC_FEAT_TEXT_INPUT` / `LLMC_FEAT_IMAGE_INPUT` / `LLMC_FEAT_AUDIO_INPUT` / `LLMC_FEAT_VIDEO_INPUT`
- `LLMC_FEAT_TEXT_OUTPUT` / `LLMC_FEAT_IMAGE_OUTPUT` / `LLMC_FEAT_AUDIO_OUTPUT` / `LLMC_FEAT_VIDEO_OUTPUT`
- `LLMC_FEAT_RERANK` / `LLMC_FEAT_RERANK_OUTPUT` / `LLMC_FEAT_DECISION_OUTPUT`

### 1. データクラスの更新
`src/llmcapa/models.py` を開き、`Capability` データクラスにデフォルト値を持つ新しいフィールドを追加します:

```python
@dataclass(frozen=True)
class Capability:
    ...
    supports_structured_outputs: bool = False
    ...
```

### 2. 代替モデルチェッカーの更新（任意）
追加する機能が、あるモデルが別のモデルを代替できるか検証する際に必須となる重要な機能である場合、`src/llmcapa/models.py` 内の `can_be_replaced_by()` の `features_to_check` リリストに追加します:

```python
    def can_be_replaced_by(self, other: "Capability", required_features: Optional[List[str]] = None) -> bool:
        ...
        if required_features is None:
            features_to_check = [
                "vision", "function_calling", "json_mode", "json_schema",
                "streaming", "reasoning", "chat_completion", "responses_api",
                "reasoning_effort", "thinking_budget", "fim", "realtime",
                "image_output", "audio_output", "video_output",
                "decision_output",  # ここに追加
            ]
            required_features = [f for f in features_to_check if self.supports(f)]
        ...
```

### 3. JSONデータファイルの更新
`src/llmcapa/data/` 配下の関連するモデルのJSONファイルに、新しいフィールドを追加します。

### 4. ユニットテストの追加
`tests/test_advanced.py` または `tests/test_registry.py` にテストケースを追加し、新しい機能フラグが正しくパース、評価、およびキャッシュされることを検証します。

---

## CLI 出力の設計

`llmcapa list` / `search` / `find` は `src/llmcapa/cli.py` の `_resolve_columns()` /
`_sort_caps()` / `_emit()` を共有します。行生成のロジックをコマンドごとに複製しないでください。

### 表示ルール

| 項目 | 挙動 |
|---|---|
| deprecated | 既定では非表示。`--all`（`--include-deprecated`）で表示し、表示時も常に有効モデルの後ろに並ぶ |
| `show` 出力 | ネストしたレコードを行展開し、`decision.question_kinds  choice, score, noul` のようにドット区切りで表示 |
| `ctx` / `out` | `-`（未確認）/ `65536` / `65.5K` / `1M`。`0` は未確認として `-` を表示する |
| `VTRJS` | vision / tools（= function_calling） / reasoning / json_mode / streaming。`-`=非対応、`?`=カタログ上未確認 |
| `*` | deprecated マーカー（テーブル表示のみ。CSV/Markdown では `deprecated` の yes/no 列に置換） |
| `$/1M in/out` | `input_per_1m`/`output_per_1m`。USD 以外は通貨コードを前置 |
| 幅 | 端末幅（非TTYは 120）に収まるよう `model_id` を優先的に `...` で切り詰め。`--wide` で無効化 |

### 機能カラム（specialized capability）

`Capability` のネストしたレコード（`image` / `audio` / `video` / `document` / `embedding` / `rerank` / `spatial` / `decision`）は `--columns` で参照できます。

| カラム | 内容 |
|---|---|
| `decision` | decision モデルかどうか（`yes` / `no` / `?` / `-`） |
| `image` `audio` `video` `document` `embedding` `rerank` `spatial` | 対応するレコードの有無 |
| `q_kinds` | `decision.question_kinds`（例 `choice,score,noul`） |
| `answers` | `decision.answer_fields` |
| `pck` | `returns_probabilities` / `returns_confidence` / `calibrated_confidence` の3スロット |
| `state` | `max_state_tokens`/`max_total_tokens`（例 `32K/64K`） |

判定ルール（`_cap_flag()`）:

1. ネストしたレコードが存在し、同名の主フィールドを持つ場合はその値（`decision.decision` など）。
2. レコードが存在し主フィールドを持たない場合は `yes`（`image` / `audio` / `video` は操作単位のレコードのため）。
3. レコードが無く、`output_modalities` に含まれる場合は `yes`。
4. レコードが無く、入力モダリティのみの場合は `?`。画像を入力できることは画像生成の可否を意味しないため、`yes` にはしない。
5. それ以外は `-`。

`--wide` は `name,in_mod,out_mod,cutoff` に加えて `decision,image,audio,video` を追加します。
`--sort` は specialized capability 名も指定できます（`yes`=1 > `-`=0 > `no` / `?`=-1。`_sort_value()` の定義どおり）。

`llmcapa find` のフィルタは `Capability.supports()` を使うため、`find image=true` は
入力モダリティとして画像を受け取るモデルも返します。カラムの `?` と一致しない場合がある点に注意してください。

### `llmcapa find`

```bash
llmcapa find decision=true
llmcapa find decision --min-context 64000 --provider typesafe
llmcapa find vision=false embedding=true --limit 20
llmcapa find --provider amazon --min-max-output 32768
```

- 位置引数は `NAME` または `NAME=BOOL`（`true/yes/y/t/1/on`・`false/no/n/f/0/off`。大文字小文字不問）。`NAME` 単独は `true`。
- `--provider` / `--min-context` / `--min-max-output` は `Registry.find()` にそのまま渡します。
- `list` / `search` と同じ描画オプション（`--format` / `--columns` / `--sort` / `--limit` / `--all` / `--wide` / `--allow-empty`）を使えます。
- 不正な真偽値は終了コード 2。

### オプション（`list` / `search` / `find` 共通）

- `--format {table,json,csv,md}` / `--json`（`--format json` の別名）
- `--columns a,b,c`（別名: `ctx`/`context_window`, `price`/`pricing`, `tools`/`function_calling` など。`_COLUMN_ALIASES` を参照）
- `--sort KEY[,KEY]`（降順は `:desc` 接尾辞、または `--sort=-ctx` 形式。`-ctx` を単独で渡すと argparse がオプションとして解釈する）
- `--limit N`（ソート後に適用。`registry.search()` 側も非 deprecated 優先でソートするため、`limit` が deprecated だけを返すことはない）
- `--all` / `--include-deprecated`
- `--wide` / `--width N`
- `--allow-empty`（0件でも終了コード0。既定は 1）

### 終了コード

| コード | 条件 |
|---|---|
| 0 | 正常（`--allow-empty` で 0 件も含む） |
| 1 | 0 件（table は stderr にメッセージ、json は `[]` を出力）、モデル未検出、取得失敗 |
| 2 | `--sort` / `--columns` の不正な値 |

JSON 出力は従来どおり `Capability.to_dict()` の全フィールドを返すため、CSV/Markdown と列構成は一致しません。

---

## 開発ワークフロー

### テストの実行
テストには `pytest` を使用します。プロジェクトのルートディレクトリから以下のコマンドを実行します:

```bash
# PYTHONPATHにsrcディレクトリを追加
set "PYTHONPATH=src;%PYTHONPATH%"
python -m pytest -v
```

### コードの検証
ビルドやコミットを行う前に、すべてのPythonファイルが正常にコンパイルできるか確認します:

```bash
python -m py_compile src/llmcapa/*.py tests/*.py
```

### パッケージのビルド
ソース配布物（sdist）とwheelバイナリをビルドする場合:

```bash
# ビルド依存関係がインストールされていない場合はインストール
pip install build hatchling

# パッケージをビルド
python -m build
```

ビルドされたファイルは `dist/` ディレクトリ配下に生成されます。

---

## Azure Catalog スクレイピング

Azure AI Foundry カタログには SSR と continuation token に関する制約があります。更新処理を変更する前に、[Azure カタログのスクレイピングノート](docs/azure_catalog_scraping.md) と `scripts/_scrape_azure_catalog.py` を確認してください。

## OpenRouter マッピング詳細

`fetch_openrouter()` が呼び出されると、OpenRouter APIのモデルスキーマは以下のように `Capability` データクラスにマッピングされます:

| 機能フィールド | OpenRouter API フィールド | マッピングロジック / フォールバック |
|---|---|---|
| `model_id` | `id` | 完全一致 |
| `display_name` | `name` | 存在しない場合は `id` にフォールバック |
| `context_window` | `context_length` | `int` にキャスト、デフォルトは `0` |
| `max_output_tokens` | `top_provider.max_completion_tokens` | `int` にキャスト、デフォルトは `0` |
| `input_modalities` | `architecture.input_modalities` | デフォルトは `["text"]` |
| `output_modalities` | `architecture.output_modalities` | デフォルトは `["text"]` |
| `provider` | — | 常に `"openrouter"`（ルートの上流名前空間は `model_id` のプレフィックスに残る） |
| `supports_function_calling` | `supported_parameters` | `"tools"` または `"function_calling"` が存在すれば `True` |
| `supports_json_mode` | `supported_parameters` | `"json_mode"`・`"response_format"`・`"structured_outputs"` のいずれかが存在すれば `True` |
| `supports_json_schema` | `supported_parameters` | `"structured_outputs"` が存在すれば `True`、それ以外は `None`（未確認） |
| `supports_reasoning` | `reasoning`（トップレベル） | 真値であれば `True` |
| `supports_reasoning_effort` | `supported_parameters` | `"reasoning"` または `"reasoning_effort"` が存在すれば `True` |
| `supports_thinking_budget` | `supported_parameters` | `"thinking"` または `"thinking_budget"` が存在すれば `True` |
| `supports_vision` | `architecture.input_modalities` | `"image"` を含めば `True` |
| `supports_streaming` / `supports_chat_completion` | — | 常に `True` |
| `supports_responses_api` | — | 常に `True`。OpenRouter のゲートウェイ転送能力であり、モデルネイティブの Responses API を意味しない |
| `pricing` | `pricing` | `prompt` と `completion` のレートを100万トークンあたりのレートに変換 |
| `aliases` | `id` | 小文字に変換された `id` がエイリアスとして追加されます |


---

## HuggingFace マッピング詳細

`fetch_huggingface()` が呼び出されると、HuggingFace API のモデルスキーマは以下のように `Capability` データクラスにマッピングされます:

| 機能フィールド | HuggingFace API フィールド | マッピングロジック / フォールバック |
|---|---|---|
| `provider` | `modelId` の `/` より前 | `org/model` の org 部分。`/` がなければ `"huggingface"` |
| `model_id` | `modelId` | `_id` にフォールバック |
| `display_name` | `modelId` | モデル ID と同一 |
| `context_window` | `cardData.model_data.context_window` / `cardData.context_window`・`context_length` / `config.max_position_embeddings`・`n_positions`・`n_ctx` | デフォルト `4096` |
| `max_output_tokens` | `cardData.model_data.max_output_tokens` / `cardData.max_output_tokens` | デフォルト `2048` |
| `input_modalities` | `pipeline_tag` | `image-text-to-text` / `visual-question-answering` / `image-feature-extraction` の場合 `["text", "image"]`、それ以外は `["text"]`。`output_modalities` は常に `["text"]` |
| `supports_vision` | `pipeline_tag` | 上記3種のいずれかなら `True` |
| `supports_chat_completion` | `pipeline_tag` | `text-generation`・`image-text-to-text`・`conversational` なら `True` |
| `supports_streaming` | — | 常に `True`（`supports_function_calling` / `supports_json_mode` は `False`） |



## データ更新ポリシー

プロバイダー別のモデルデータを更新する際は、データの出所を混同しないこと。

- `openrouter.json` には OpenRouter から取得したモデルデータだけを格納する。
- OpenRouter のデータを、他プロバイダーのデータファイル（`google.json`、`anthropic.json` など）へ流用・上書きしてはならない。
- 他プロバイダーのデータは、原則として各プロバイダーの公式 API、公式ドキュメント、または当該プロバイダー専用の更新スクリプトから取得する。
- 複数プロバイダーを更新する場合も、プロバイダーごとに取得・内容確認・差分確認を行う。一括処理で OpenRouter データを他プロバイダーへ配布してはならない。
- 更新前に既存の未コミット変更を確認し、必要に応じてバックアップを作成する。

## Modellix 集約カタログ

Modellix は LLM ゲートウェイと画像・動画・音声のメディア API を提供する集約サービスです。Bundled catalog では、次の2ファイルを別々の出所として管理します。

- `src/llmcapa/data/modellix.json`: 公式 LLM カタログのスナップショット（29件）
- `src/llmcapa/data/modellix_media.json`: 公式ドキュメントインデックス由来のメディアモデル（178件）

両ファイルの `provider` は `modellix` とし、上流プロバイダーはモデルIDのプレフィックス（例: `kling/kling-v3-t2v`）に保持します。Modellix は集約カタログなので、ネイティブプロバイダーのデータを上書きしないよう、`Registry._load_bundled()` では集約ファイル群（`openrouter.json`、`novita.json`、`azure_foundry.json`、`lmstudio.json`、`ollama.json`、`modellix.json`、`modellix_media.json`）として最後にロードします。flat な `_models` 側は first-registered-wins のため、ネイティブ側が優先されます。

更新時の参照先は `https://docs.modellix.ai/llms.txt`、`https://www.modellix.ai/llm`、および Modellix の公式モデルドキュメントです。OpenRouter のデータを Modellix カタログへ流用してはなりません。メディアモデルはトークン系の `context_window` / `pricing` が提供されない場合があるため、未確認値は推測で補完せず `0` または `null` とし、モダリティと公式ドキュメントURLを `extra` に記録します。
