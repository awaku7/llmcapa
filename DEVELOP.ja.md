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
│   ├── registry.py         # インメモリレジストリ、ロード、およびOpenRouter取得
│   ├── cli.py              # コマンドラインインターフェース
│   └── data/               # 同梱されているオフライン機能データ (JSON)
│       ├── __init__.py
│       ├── openai.json
│       ├── anthropic.json
│       └── ...
└── tests/                  # ユニットテスト (pytest)
    ├── test_registry.py
    ├── test_cache.py
    └── test_advanced.py
```

---

## 設計思想

1. **オフラインファースト**: すべてのコア機能データは、パッケージ内にJSONファイルとして静的に同梱されています。標準的な検索時にネットワークリクエストは発生しません。
2. **実行時依存関係ゼロ**: ライブラリはPython標準ライブラリのみで動作する必要があります。外部パッケージ（`pytest` や `build` など）は、開発およびテスト専用です。
3. **不変性とパフォーマンス**: `Capability` データクラスは `frozen=True` です。機能チェック時の冗長な計算を避けるため、評価結果はメモ化（内部キャッシュ）されます。

---

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

### 2. プロバイダーテストリストの更新
`tests/test_registry.py` を開き、`test_providers()` 内の `expected` セットに新しいプロバイダー名を追加します:

```python
def test_providers():
    provs = llmcapa.providers()
    expected = {
        "openai", "anthropic", "google",
        "xai", "meta", "mistral", "qwen", "deepseek", "nvidia",
        "microsoft", "amazon", "ntt", "customer-cloud", "elyza",
        "softbank", "nec", "fujitsu", "pfn",
        "cohere",  # ここに追加
    }
    assert expected <= set(provs)
```

---

## 新しい機能フラグの追加

新しい機能フラグ（例: `supports_structured_outputs`）を追加する場合:

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
                "vision", "function_calling", "json_mode", "streaming",
                "reasoning", "chat_completion", "responses_api",
                "reasoning_effort", "thinking_budget", "image_output",
                "audio_output", "video_output",
                "structured_outputs"  # ここに追加
            ]
            required_features = [f for f in features_to_check if self.supports(f)]
        ...
```

### 3. JSONデータファイルの更新
`src/llmcapa/data/` 配下の関連するモデルのJSONファイルに、新しいフィールドを追加します。

### 4. ユニットテストの追加
`tests/test_advanced.py` または `tests/test_registry.py` にテストケースを追加し、新しい機能フラグが正しくパース、評価、およびキャッシュされることを検証します。

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
| `supports_function_calling` | `supported_parameters` | `"tools"` または `"tool_choice"` が存在すれば `True` |
| `supports_json_mode` | `supported_parameters` | `"structured_outputs"` または `"response_format"` が存在すれば `True` |
| `supports_reasoning` | `supported_parameters` | `"reasoning"` または `"include_reasoning"` が存在すれば `True` |
| `supports_reasoning_effort` | `supported_parameters` | `"reasoning"` が存在すれば `True` |
| `pricing` | `pricing` | `prompt` と `completion` のレートを100万トークンあたりのレートに変換 |
| `aliases` | `id` | 小文字に変換された `id` がエイリアスとして追加されます |
