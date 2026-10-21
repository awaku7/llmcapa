# llmcapa モデルカタログ一括更新（GitHub Actions）

## 最初に

この仕組みは、各プロバイダーの**公式ソース**からモデルカタログを更新し、変更結果を一覧化してPRを作成するためのものです。更新された内容は**自動マージしません**。

## 実行手順（ブラウザーのみ）

1. GitHub の [llmcapa リポジトリ](https://github.com/awaku7/llmcapa)を開きます。
2. 上部の **Actions** を選択します。
3. 左側の **Refresh all model catalogs** を選びます。
4. **Run workflow** を押し、ブランチを **main** にします。
5. Provider に **all**（初期値）を指定して、**Run workflow** を実行します。
6. 実行履歴を開いて、各プロバイダーの成功・失敗と生成されたレポートを確認します。
7. 差分がある場合は新しいPRが作成されます。**Files changed** と **Checks**、レポートを確認してからマージしてください。

公式ソースを更新する権限や対応する公開APIがない場合は、そのプロバイダーのみ失敗として報告され、以前のデータは保持されます。すべての公式サイトが常に取得可能とは限りません。

### 特定のプロバイダーのみ更新

Provider に `openai`、`anthropic`、`google`、`xai` などを指定します。指定できるキーは次のコマンドで確認できます。

```bash
python scripts/_update_all_providers.py --list
```

## 出力

- **Actions > 実行履歴 > Summary**: 更新結果の概要とモデル差分
- **Artifacts**: 完全な `report.md`、`report.json`、プロバイダー別ログ
- **自動作成PR**: データJSONに加えて、`docs/catalog_refresh/latest.md` と `docs/catalog_refresh/latest.json` を更新

差分はモデルごとに追加・変更・削除を区別し、変更では入出力モダリティ、料金、コンテキスト長、機能フラグなどの**変更されたフィールド名**を記録します。全結果はJSONでプログラムからも利用できます。

JSONの差分は、モデルIDを基準に比較します。JSONファイル内の並べ替えだけではデータ変更として扱いません。

## 安全策

- OpenRouterを使って他プロバイダーのJSONを更新しません。各プロバイダー専用の更新スクリプトを順次呼び出します。
- 失敗やタイムアウト時にはその回の作業ファイルを復元します。前に成功した更新は残ります。
- 内容が空、モデルIDが重複、既存モデルの20%超（少数カタログでは2件以上）が消える場合は更新を拒否します。これは正式な廃止でも確認が必要な安全策です。
- 他プロバイダーのファイルなど、意図しない追跡対象ファイルの変更を検出したら、その更新を拒否します。
- モデル情報に推測を混ぜず、各専用更新スクリプトの一次ソースに依存します。
- 結果が変わらない場合、PRは作成しません。
- PRを自動マージせず、Black・Ruff・更新処理の単体テスト・回帰テスト・既存CIで検証します。
- 回帰テストの失敗はPRに明示されます。失敗が残る場合はそのPRをマージしないでください。

一括更新のジョブは最大240分、各プロバイダーは最大180秒で打ち切ります。更新対象が多い場合や公式サイトが低速な場合、すべて取得できる保証はありません。

## 初回設定・制約

GitHub Actions の有効化と、リポジトリの **Settings > Actions > General** にある「Allow GitHub Actions to create and approve pull requests」の許可が必要です。組織・リポジトリの権限設定によっては変更できない場合があります。

更新ジョブは`GITHUB_TOKEN`で作業ブランチをpushし、PRを作成します。GitHubの仕様上、`GITHUB_TOKEN`が作成したPRは通常の`pull_request`ワークフローを自動起動しないため、更新後に`ci.yml`を明示的に実行します。

ブラウザー操作が必要な公式カタログのためにPlaywright/Chromiumをインストールします。**Vertex AI**など追加SDK、認証情報、その他特別な依存が必要な更新は失敗として記録される場合があります。認証情報をレポートやPRに転記しないでください。

## ローカル実行・検証

```bash
python -m pip install -e . pytest black ruff requests playwright
python -m playwright install chromium
python scripts/refresh_catalogs.py --provider all
python -m black --check scripts/refresh_catalogs.py tests/test_refresh_catalogs.py
python -m ruff check scripts/refresh_catalogs.py tests/test_refresh_catalogs.py
python -m pytest -q tests/test_refresh_catalogs.py
```

ローカル実行ではカタログの変更がGitのステージング領域に残ります。PR作成とプッシュは行いません。**作業前に必ずクリーンな作業ツリーを用意してください。**
