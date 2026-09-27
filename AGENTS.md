# エージェント向け開発ガイド

このファイルは、`llmcapa` リポジトリで作業するエージェント向けの要点です。詳細・最新の仕様は [`DEVELOP.ja.md`](DEVELOP.ja.md) と関連テストを参照してください。両者が食い違う場合は、実装・テストの現状を確認し、必要ならユーザーに確認してください。

## プロジェクトの基本方針

- **オフラインファースト**: 標準の検索・参照処理でネットワークアクセスを発生させないでください。モデルカタログは `src/llmcapa/data/*.json` に同梱します。
- **実行時依存ゼロ**: ライブラリ本体は Python 標準ライブラリのみで動作させます。外部依存は開発・テスト用途に限ります。
- `Capability` は不変（`frozen=True`）なデータモデルです。既存の型、デフォルト値、キャッシュ設計を尊重してください。
- 変更は対象範囲を絞り、既存の公開 API と後方互換性を保つようにしてください。

## 変更前・変更後の確認

1. 変更前に `git status` を確認し、ユーザーの未コミット変更を上書き・巻き戻ししないでください。データ更新前には特に差分とバックアップの必要性を確認します。
1. 関連実装・テスト・ドキュメントを確認してから変更してください。カタログや機能の値は推測で埋めず、根拠のある情報だけを記録します。不明な値は既存スキーマに従って `null` / `0` / 未設定とします。
1. 変更に対応するテストを追加・更新し、可能な範囲でテストと構文検証を実行します。実行できなかった検証は、完了報告で明示してください。
1. 最終報告では、変更点と実行した検証を簡潔に示してください。依頼されていないコミットや破壊的操作は行いません。

## 主なコード配置

- `src/llmcapa/models.py`: `Capability`、Feature、機能評価・代替判定
- `src/llmcapa/specialized_capabilities.py`: document / embedding / rerank / spatial / decision などの型
- `src/llmcapa/registry.py`: カタログ読み込み、プロバイダー解決、検索、取得、外部 API 取得
- `src/llmcapa/cli.py`: CLI のコマンドと出力
- `src/llmcapa/tokenizer.py`: オフラインのプロバイダー別トークンカウント
- `src/llmcapa/data/`: 同梱カタログ JSON
- `scripts/`: プロバイダー別の更新・スクレイプ・後処理
- `tests/`: pytest テスト

## カタログ・プロバイダーのルール

- プロバイダー別カタログは、原則としてそのプロバイダーの公式 API、公式ドキュメント、専用更新スクリプトを一次ソースにします。
- **OpenRouter のデータから構築してよいのは `openrouter.json` のみ**です。他プロバイダーのカタログに OpenRouter の情報を流用・上書きしないでください。複数カタログの一括更新でも、各プロバイダーを個別の公式ソースで処理します。
- `scripts/openrouter_providers/` のシムは歴史的参照用です。現役の更新スクリプトから import しないでください。
- `fetch_github_catalog(provider, ...)` は公開リポジトリ `awaku7/llmcapa` の正規化済みカタログを取得します。プロバイダー指定の `get()` / `search()` が miss した場合も、プロバイダーごとにレジストリ内で一度だけ取得を試み、1回だけ再検索します。通常のヒットとプロバイダー未指定の検索はオフラインです。既定では取得したJSONで対応する同梱カタログを更新し、更新前のファイルを `~/.llmcapa/github_catalog_backups` にバックアップします。書き込み不可、または `write_bundled=False` の場合は永続的なユーザーカタログ `~/.llmcapa/catalogs/github` に保存し、次回起動時に同梱データより優先して読み込みます。ユーザー上書きの削除でリセットできます。24時間の通信キャッシュとは別です。公式ソースからのカタログ生成・検証手順は引き続き維持してください。
- 新しいプロバイダーを追加する場合は、`src/llmcapa/data/<provider>.json` を作成し、`providers()` / `list_models()` / `get()` で登録・取得できるテストを `tests/test_registry.py` に追加します。更新スクリプトや別の登録処理が必要かも既存実装で確認してください。
- `get()`、`list_models()`、`search()` のプロバイダー名は正規化・エイリアス解決されます。エイリアスを追加する場合は `registry.py` の `_provider_aliases` と `tests/test_registry.py` の両方を更新します。
- `search(provider=None)` は全プロバイダーを走査し、同じ model ID が複数プロバイダーにある場合も保持する仕様です。変更時は `list_models` / `_by_provider` 経由の動作を確認してください。
- 集約カタログのロード順や first-registered-wins の挙動を変える場合は、ネイティブカタログとの優先順位を必ず検証してください。Modellix の `modellix.json` と `modellix_media.json` は別々の公式ソースとして扱い、OpenRouter データで代用しません。
- 画像入力だけで画像生成対応と判断しないでください。画像・音声・動画などの未確認メタデータは、専用後処理の保守的な判定に従います。

## 機能・CLI の変更

- 新しい機能フラグは `Capability` のデフォルト値、必要に応じた `can_be_replaced_by()` の必須機能一覧、関連するカタログ JSON、パース・評価・キャッシュを確認するテストを一貫して更新します。
- `list` / `search` / `find` の表示ロジックは `cli.py` の共有処理（`_resolve_columns()` / `_sort_caps()` / `_emit()`）を利用し、コマンドごとに重複実装しないでください。
- specialized capability の表示・フィルターは、入力モダリティと出力・操作レコードの意味の違い、および未確認を表す `?` を保ってください。特に入力画像対応は画像生成対応を意味しません。
- CLI の変更では、既定の deprecated モデル除外、並び順、出力形式、空結果や不正引数の終了コードを既存テストに合わせて維持してください。

## 検証コマンド

リポジトリのルートで実行します。

```bat
set "PYTHONPATH=src;%PYTHONPATH%"
python -m pytest -v
python -m py_compile src/llmcapa/*.py tests/*.py
```

パッケージビルドが変更内容に関係する場合:

```bat
python -m build
```

## 特記事項

- Azure AI Foundry のスクレイピングを変更する前に [`docs/azure_catalog_scraping.md`](docs/azure_catalog_scraping.md) と `scripts/_scrape_azure_catalog.py` を確認してください。
- OpenAI / OpenRouter / HuggingFace / Modellix の更新元とマッピング、CLI の詳細、各機能の追加手順は [`DEVELOP.ja.md`](DEVELOP.ja.md) を参照してください。
