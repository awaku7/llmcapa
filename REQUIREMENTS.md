# llmcapa 要件定義（ドラフト）

## 目的
各種 LLM モデルの capability（能力・制約）を統一的な API で取得できる Python ライブラリを提供する。
pip でインストール可能なパッケージとして配布する。

## 基本方針
- オフラインファースト: capability データはパッケージ内に静的データ（JSON）として同梱し、ネットワーク接続なしで動作する。
- データとロジックを分離し、データ更新のみでモデル追加に対応できる構造にする。
- I18N 対応: メッセージ・説明文は将来の多言語化を考慮した構造にする。

## 対象プロバイダ（初期）
- OpenAI（GPT-4o, GPT-4.1, o1/o3 系 など）
- Anthropic（Claude 3.5/3.7/4 系）
- Google（Gemini 1.5/2.0/2.5 系）
- ※ データ追加でその他プロバイダ（Meta Llama, Mistral, Cohere 等）を拡張可能

## capability 項目
| 項目 | 型 | 例 |
|---|---|---|
| provider | str | "openai" |
| model_id | str | "gpt-4o" |
| display_name | str | "GPT-4o" |
| context_window | int | 128000 |
| max_output_tokens | int | 16384 |
| input_modalities | list[str] | ["text", "image"] |
| output_modalities | list[str] | ["text"] |
| supports_function_calling | bool | true |
| supports_json_mode | bool | true |
| supports_streaming | bool | true |
| supports_vision | bool | true |
| supports_reasoning | bool | false |
| knowledge_cutoff | str (YYYY-MM) | "2023-10" |
| pricing | dict (任意) | {"input_per_1m": 2.5, "output_per_1m": 10.0, "currency": "USD"} |
| deprecated | bool | false |
| aliases | list[str] | ["gpt-4o-2024-08-06"] |

## 公開 API（案）
```python
import llmcapa

# 単一モデルの capability 取得（alias でも解決可）
cap = llmcapa.get("gpt-4o")
cap.context_window        # 128000
cap.supports("vision")    # True

# モデル一覧
llmcapa.list_models()                      # 全モデル
llmcapa.list_models(provider="anthropic")  # プロバイダ絞り込み

# 条件検索
llmcapa.find(supports_vision=True, min_context_window=100000)

# ユーザー定義データの追加/上書き（ローカル JSON 読み込み）
llmcapa.load_extra("my_models.json")
```

## CLI（案）
```
llmcapa show gpt-4o
llmcapa list --provider openai
llmcapa list --json
```

## パッケージ構成
```
llmcapa/
├── pyproject.toml        # setuptools or hatchling, PEP 621
├── README.md
├── LICENSE               # MIT
├── src/llmcapa/
│   ├── __init__.py       # 公開 API
│   ├── models.py         # Capability dataclass
│   ├── registry.py       # データ読み込み・検索
│   ├── cli.py            # CLI エントリポイント
│   └── data/
│       ├── openai.json
│       ├── anthropic.json
│       └── google.json
└── tests/
    └── test_registry.py
```

## 配布
- ビルドバックエンド: hatchling（pyproject.toml のみで完結）
- `pip install llmcapa` / `pip install .` / wheel ビルド対応
- Python >= 3.9
- 実行時依存: なし（標準ライブラリのみ）

## テスト
- pytest による単体テスト
- 全 JSON データのスキーマ検証テスト

## 未決事項（要確認）
1. パッケージ名は `llmcapa` でよいか
2. pricing 情報を含めるか（変動が激しいため任意項目とする案）
3. ライセンス（MIT 想定）
