# 画像モデル Capability 仕様案

## 1. 目的

画像生成・画像編集モデルのAPI差分を、利用側が個別のモデル名判定や文字列のハードコードなしに参照できるようにする。

対象例:

- OpenAI GPT Image 系
- Google Imagen 系
- xAI / Grok Imagine 系
- Meta 画像生成系
- その他、画像生成または画像編集APIを提供するモデル

本仕様は、単なる `image_input` / `image_output` の有無だけでは表現できない、画像API固有の能力と制約を扱う。

## 2. 設計方針

### 2.1 `Capability` と画像Capabilityを分離する

既存の `Capability` に大量の画像専用フィールドを追加するのではなく、画像機能を表す専用の構造体を追加する。

```python
@dataclass(frozen=True)
class Capability:
    # 既存フィールド
    ...
    image: ImageCapability | None = None
```

`image is None` は「画像Capability情報が未登録または対象外」を表す。

### 2.2 不明と非対応を区別する

- `None`: 情報なし、未確認
- `False`: 公式仕様上、非対応
- `True`: 公式仕様上、対応

一覧型の値についても、空配列を「非対応」と解釈せず、Capability自体が存在するかどうかで判断する。

### 2.3 APIエンドポイント単位で管理する

同じモデルでも、Image API、Responses API、Chat Completionsなどで使える機能が異なる場合がある。したがって、モデル全体のCapabilityとエンドポイントCapabilityを混同しない。

## 3. 提案データモデル

### 3.1 `ImageCapability`

画像生成系と画像理解系は、同じ画像モデルでも異なるため、画像理解の詳細は別構造に分離する。

```python
@dataclass(frozen=True)
class ImageAnalysisCapability:
    embedding: bool | None = None
    classification: bool | None = None
    object_detection: bool | None = None
    segmentation: bool | None = None
    captioning: bool | None = None
    ocr: bool | None = None


@dataclass(frozen=True)
class ImageCapability:
    analysis: ImageAnalysisCapability | None = None

    # 基本機能
    generation: bool | None = None
    editing: bool | None = None
    inpainting: bool | None = None
    outpainting: bool | None = None
    image_variation: bool | None = None

    # 入力
    accepts_text_prompt: bool | None = None
    accepts_image_input: bool | None = None
    accepts_file_id: bool | None = None
    accepts_image_url: bool | None = None
    accepts_data_url: bool | None = None
    max_input_images: int | None = None
    input_formats: tuple[str, ...] = ()
    input_mime_types: tuple[str, ...] = ()
    max_input_bytes: int | None = None
    max_input_payload_bytes: int | None = None
    max_input_file_bytes: int | None = None
    max_input_width: int | None = None
    max_input_height: int | None = None
    max_input_pixels: int | None = None
    input_fidelity_values: tuple[str, ...] = ()

    # 出力と生成数
    output_formats: tuple[str, ...] = ()
    response_formats: tuple[str, ...] = ()
    max_outputs: int | None = None
    supports_transparent_background: bool | None = None
    background_values: tuple[str, ...] = ()

    # 品質
    quality_values: tuple[str, ...] = ()

    # サイズ
    supports_arbitrary_size: bool | None = None
    supported_sizes: tuple[str, ...] = ()
    size_divisible_by: int | None = None
    min_width: int | None = None
    max_width: int | None = None
    min_height: int | None = None
    max_height: int | None = None
    min_aspect_ratio: float | None = None
    max_aspect_ratio: float | None = None

    # ストリーミング
    supports_streaming: bool | None = None
    partial_images_min: int | None = None
    partial_images_max: int | None = None

    # 入力テキスト
    prompt_max_chars: int | None = None

    # 出典・状態
    source_url: str | None = None
    checked_at: str | None = None
    status: str = "documented"
```

### 3.2 エンドポイントCapability

必要に応じて、以下のようなエンドポイント別情報を持たせる。

```python
@dataclass(frozen=True)
class ImageEndpointCapability:
    image_api_generations: bool | None = None
    image_api_edits: bool | None = None
    responses_image_tool: bool | None = None
    chat_completions: bool | None = None
    batch: bool | None = None
    responses_mainline_model_required: bool | None = None
    responses_action_values: tuple[str, ...] = ()
    responses_multi_turn: bool | None = None
    responses_image_context: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)
```

`ImageCapability` に `endpoints: ImageEndpointCapability | None` として追加する。

## 4. GPT-Image-2.5 Flare の登録例

```json
{
  "generation": true,
  "editing": true,
  "inpainting": true,
  "accepts_text_prompt": true,
  "accepts_image_input": true,
  "accepts_file_id": true,
  "accepts_image_url": true,
  "max_input_images": 16,
  "input_fidelity_values": ["low", "high"],
  "output_formats": ["png", "jpeg", "webp"],
  "response_formats": ["b64_json"],
  "max_outputs": 10,
  "background_values": ["auto", "opaque", "transparent"],
  "supports_transparent_background": true,
  "quality_values": ["auto", "low", "medium", "high", "xhigh", "max"],
  "supports_arbitrary_size": true,
  "supported_sizes": ["1024x1024", "1536x1024", "1024x1536"],
  "size_divisible_by": 16,
  "min_aspect_ratio": 0.333333,
  "max_aspect_ratio": 3.0,
  "supports_streaming": true,
  "partial_images_min": 0,
  "partial_images_max": 3,
  "prompt_max_chars": 32000,
  "source_url": "https://developers.openai.com/api/docs/models/gpt-image-2.5-flare.md",
  "status": "documented"
}
```

任意サイズの上限や現在のピクセル制限は、モデル・APIバージョンによって変動し得るため、固定値として登録できない場合は `extra` または別の制約オブジェクトに保持する。

## 5. GPT-Image-2.5 Sunburst との差分

| Capability | Flare | Sunburst |
|---|---:|---:|
| テキストから生成 | 対応 | 対応 |
| 画像編集 | 対応 | 対応 |
| Inpainting | 対応 | 対応 |
| 透明背景 | 対応 | 対応 |
| `xhigh` / `max` | 対応 | 対応 |
| 任意サイズ | 対応 | 対応 |
| 主な位置付け | 高速な日常生成 | 編集精度重視 |

性能差や速度差のようなベンチマーク結果は、静的Capabilityではなく、説明メタデータまたは別の評価データとして扱う。

## 6. 既存Capabilityとの互換性

既存の以下の判定は維持する。

```python
cap.supports("image_input")
cap.supports("image_output")
cap.supports("vision")
```

画像Capabilityは追加情報として利用する。

```python
cap.image is not None
cap.image.generation is True
"xhigh" in cap.image.quality_values
"webp" in cap.image.output_formats
```

既存のJSONデータに `image` がない場合も、従来どおり読み込めるようにする。

## 7. UAGでの利用方法

UAGは、画像ツールのスキーマおよびリクエスト生成時にllmcapaの情報を参照する。

### 7.1 ツール入力の動的制約

- `quality` のenumを `quality_values` から生成
- `output_format` のenumを `output_formats` から生成
- `n` の最大値を `max_outputs` から設定
- ストリーミング引数は `supports_streaming` が真の場合だけ公開
- `mask_path` は `inpainting` が真の場合だけ公開
- 画像参照枚数を `max_input_images` で検証

### 7.2 リクエスト生成

UAGは未対応のパラメータを送らない。

例:

```python
if image_capability is not None:
    if quality and quality not in image_capability.quality_values:
        raise ValueError("unsupported image quality")
    if output_format and output_format not in image_capability.output_formats:
        raise ValueError("unsupported output format")
```

ただし、APIキーの権限、契約、地域、利用枠、APIバージョンはllmcapaでは判定せず、実行時エラーとして扱う。

## 8. 登録データの出典と更新

各画像Capabilityには、可能な限り以下を保持する。

- 公式仕様URL
- 確認日時
- モデルの固定スナップショット
- `documented` / `preview` / `deprecated` などの状態
- APIバージョンまたはスナップショット

公式ドキュメントにない推測値は、正式なCapabilityとして登録しない。

更新処理はプロバイダー別パーサーで行う。`scripts/_scrape_image_capabilities.py` にAmazon、Google、ByteDance、xAI、Qwen、MiniMax、Meta、Microsoftの公式ページ用パーサーを持ち、各プロバイダーの更新スクリプト完了後に実行する。`_update_all_providers.py` と `_postprocess_catalogs.py` からも同じ処理を呼び出せる。

ページ取得失敗、レイアウト変更、仕様未記載の項目はエラー扱いにせず、既存値を保持して未設定のままとする。

## 9. 実装手順

1. `models.py` に `ImageCapability` と `ImageEndpointCapability` を追加
2. `Capability.image` を末尾に追加し、既存の位置引数互換性を維持
3. `from_dict` / `to_dict` でtuple、nullable値を正規化
4. OpenAIのGPT Imageモデルを登録
5. Flare、Sunburst、GPT-Image-1で単体テストを追加
6. 旧形式JSONの読み込みテストを追加
7. 各プロバイダー更新スクリプトから公式画像仕様パーサーを呼び出す
8. 画像入力形式、MIME、ファイルサイズ、ペイロードサイズ、画素数を明示値だけ登録
9. UAG側で画像ツールの品質・形式・ストリーミング制約を動的参照
10. 未登録モデルでは従来の保守的な挙動にフォールバック

## 10. テスト項目

- `gpt-image-2.5-flare` が画像生成・編集・inpainting対応として解決できる
- `xhigh` / `max` が品質候補に含まれる
- `jpeg` / `webp` が出力候補に含まれる
- `transparent` が背景候補に含まれる
- `max_outputs == 10` が取得できる
- `max_input_images == 16` が取得できる
- `partial_images_max == 3` が取得できる
- 非画像モデルの `image` が `None` または非対応になる
- 旧Capability JSONが壊れずに読み込める
- 未知の画像モデルで例外を起こさず、unknownとして扱える

## 11. 実装しないもの

以下はモデルCapabilityではなく、実行環境または別データとして扱う。

- APIキーの有効性
- 組織認証の完了状況
- 地域ごとの提供可否
- 現在のレート制限
- 残りクレジット
- 実測の生成速度
- 実測の画質ランキング
- プロンプト安全性判定の詳細

これらを静的なモデルCapabilityに混ぜると、モデル仕様とアカウント状態が混同されるためである。


## 12. プロバイダー別の画像モデル

### 12.1 目的

画像Capabilityの共通スキーマを定義した上で、プロバイダーごとのモデル登録例とAPI差分を整理する。モデル名に `image` が含まれるかどうかだけで判定せず、必ず登録されたCapabilityを正規情報源とする。

以下は、llmcapa 0.5.28 の登録モデルおよび既存アダプターを基準にした分類である。実際の提供状況、アカウント権限、地域、APIバージョンは別途確認する。

### 12.2 直接APIを提供するプロバイダー

| プロバイダー | 代表的な画像モデル | 主な用途 | 登録上の注意 |
|---|---|---|---|
| OpenAI | `gpt-image-1`, `gpt-image-1.5`, `gpt-image-2`, `gpt-image-2.5-flare`, `gpt-image-2.5-sunburst` | 生成、編集、inpainting | Image APIのgeneration/editをエンドポイント別に記録する |
| Google | `gemini-2.5-flash-image`, `gemini-3-pro-image`, `gemini-3.1-flash-image` | 会話型画像生成・編集 | Geminiの画像入出力とImagenの生成APIを区別する |
| Vertex AI | Imagen系、Vertex上の画像モデル | 生成、編集 | Google本体のモデル名とVertexのデプロイ名を混同しない |
| Amazon Bedrock | `nova-canvas-v1`, `titan-image-generator-v2`, `nova-2-omni-v1` | 生成、画像理解 | BedrockモデルID、入力形式、リージョン差を保持する |
| xAI | `grok-imagine-image`, `grok-imagine-image-quality` | 画像生成・編集 | 生成品質や編集APIの差分をモデルごとに記録する |
| Meta | `muse-image-1.0` | 画像生成 | Responses APIとImage APIの利用形態を分けて記録する |
| Z.AI | `glm-image` | 画像生成 | SDK/APIの出力形式、サイズ制約を別途記録する |
| Black Forest Labs | FLUX系、`FLUX.2-*` | 画像生成・編集 | モデル系列ごとに編集、参照画像、サイズ対応を確認する |
| ByteDance | Seedream系 | 画像生成・編集 | `seedream`のバージョンごとにAPI差分があるため固定IDで登録する |
| Qwen | Qwen Image系 | 画像生成・編集 | モデルIDとホスティング先を分離する |

### 12.3 アグリゲーター・ホスティングプロバイダー

OpenRouter、Together、NVIDIA、Hugging Faceなどは、プロバイダー自身が画像モデルの仕様を決めるとは限らない。下位モデルのCapabilityを参照できるようにする。

```text
実行プロバイダー: together
モデルID: black-forest-labs/FLUX.2-pro
Capabilityの正規モデル: black-forest-labs/FLUX.2-pro
```

登録時は次の情報を分離する。

- `provider`: 実際にリクエストを送る先
- `model_id`: 送信するモデルID
- `capability_source`: 仕様を定義するモデルまたは公式提供元
- `endpoint`: そのプロバイダーで利用可能なAPI

同じモデル名でも、プロバイダーごとに以下が異なる可能性がある。

- 対応パラメータ
- 出力形式
- 最大画像数
- サイズ制約
- ストリーミング可否
- 入力画像の指定方法

したがって、モデルCapabilityとプロバイダー・エンドポイントCapabilityの両方を保持する。

### 12.4 Azure OpenAI

Azure OpenAIは独立したモデル仕様ではなく、OpenAIモデルをデプロイ名で公開するラッパーとして扱う。

```text
source_provider: openai
runtime_provider: azure
source_model: gpt-image-2.5-flare
deployment_name: my-gpt-image-flare
```

Azure固有のAPIバージョン、リージョン、デプロイ状態は、モデルCapabilityではなくランタイム設定に保持する。

### 12.5 画像理解専用モデルとの区別

以下のようなモデルは画像を扱うが、必ずしも画像生成モデルではない。

- CLIPの画像・テキスト埋め込み
- 画像分類モデル
- 物体検出モデル
- 画像キャプションモデル
- OCRモデル
- 医用画像解析モデル

そのため、次のCapabilityを別々に判定する。

```python
cap.supports("image_input")
cap.supports("image_output")
cap.image.generation
cap.image.editing
cap.image.inpainting
cap.image.analysis.embedding
cap.image.analysis.classification
cap.image.analysis.captioning
```

画像出力があるだけでは画像生成対応とはみなさない。

### 12.6 プロバイダー別登録の最小例

```json
{
  "provider": "xai",
  "model_id": "grok-imagine-image",
  "input_modalities": ["text", "image"],
  "output_modalities": ["image"],
  "image": {
    "generation": true,
    "editing": true,
    "output_formats": ["png", "jpeg", "webp"],
    "quality_values": ["auto", "standard", "high"],
    "source_url": "https://docs.x.ai/"
  },
  "extra": {
    "capability_source": "xai"
  }
}
```

公式仕様が確認できない項目は推測値で埋めず、`None` または未設定とする。

### 12.7 登録優先順位

画像モデルの登録は、次の優先順位で行う。

1. 公式モデル仕様ページ
2. 公式APIリファレンス
3. 公式SDKの型定義・スキーマ
4. 公式モデル一覧
5. 信頼できるプロバイダーのモデルメタデータ
6. 非公式情報（正式Capabilityには使用しない）

プロバイダーのモデル一覧に存在するだけでは、生成・編集機能の登録根拠としては不十分とする。
