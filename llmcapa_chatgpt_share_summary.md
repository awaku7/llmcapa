# llmcapa向け Computer Use capability 設計メモ

## 1. 概要

- 出典: [ChatGPT共有会話](https://chatgpt.com/share/6a7fde40-02c4-83e9-845a-3f582781f547)
- 目的: llmcapa で、各モデル・プロバイダーが Computer Use / CUA（画面認識、マウス、キーボード操作など）をどの程度サポートするかを機械的に判定できるようにする。
- 方針: 単純な `supports_computer_use: bool` ではなく、ツール形式、バージョン、実行環境、アクション、提供方式を含む構造化 capability として管理する。

> この文書は共有会話内の提案を実装向けに整理したもの。プロバイダー名、モデル名、API 名、ツールバージョン、ベータヘッダーは変更される可能性があるため、実装時に必ず公式ドキュメントで再確認する。

## 2. 解決したい問題

現在のモデル capability は、推論、最大トークン数、プロバイダー、モデル名などの判定が中心で、Computer Use の可否を十分に表現できない。

Computer Use では、少なくとも次を区別する必要がある。

1. モデルが Computer Use をサポートしているか
2. プロバイダーがネイティブ CUA を提供しているか
3. llmcapa/UAG 側の Computer Tool で代替できるか
4. API が要求する tool type・バージョン・ベータヘッダー
5. デスクトップ、ブラウザー、モバイルなどの対象環境
6. クリック、入力、スクロール、ドラッグ、ズームなどの個別アクション
7. GA、Beta、Preview、Legacy、Deprecated などの提供状態

## 3. 正規化モデル

### 3.1 `ComputerUseCapability` の例

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ComputerUseCapability:
    supported: bool
    native: bool
    provider: str
    model: str
    api_type: Optional[str] = None
    tool_type: Optional[str] = None
    tool_version: Optional[str] = None
    status: str = "unknown"  # ga/beta/preview/legacy/deprecated/retired/unknown
    environments: frozenset[str] = field(default_factory=frozenset)
    actions: frozenset[str] = field(default_factory=frozenset)
    requires_beta: bool = False
    beta_header: Optional[str] = None
    enable_zoom: bool = False
    source_url: Optional[str] = None
```

### 3.2 フィールドの意味

| フィールド | 意味 |
|---|---|
| `supported` | Computer Use 機能を利用可能か |
| `native` | モデル/API がネイティブに提供するか。`False` は UAG 側のツール利用など |
| `provider` / `model` | 判定対象のプロバイダーとモデル |
| `api_type` | Responses API、Messages API などの API 種別 |
| `tool_type` | プロバイダー固有の Computer Tool 名 |
| `tool_version` | Computer Tool のバージョン。モデルバージョンとは分離する |
| `status` | `ga`、`beta`、`preview`、`legacy`、`deprecated`、`retired`、`unknown` |
| `environments` | `desktop`、`browser`、`mobile`、`remote_desktop` など |
| `actions` | `screenshot`、`left_click`、`type`、`key`、`scroll`、`drag`、`zoom` など |
| `requires_beta` | ベータ指定が必要か |
| `beta_header` | 必要なベータヘッダー |
| `enable_zoom` | ズーム操作を有効化できるか |
| `source_url` | capability の根拠となる公式ドキュメント URL |

### 3.3 推奨アクション集合

```text
screenshot
left_click
right_click
middle_click
double_click
triple_click
mouse_move
type
key
scroll
left_click_drag
left_mouse_down
left_mouse_up
hold_key
wait
zoom
```

プロバイダーが対応していないアクションは、実行前に capability で拒否する。特に `zoom` はツールバージョンによる差異が出やすいため、個別フラグまたは `actions` で明示する。

## 4. ネイティブ CUA と UAG Computer Tool の区別

### ネイティブ CUA

モデルプロバイダーが Computer Tool を API の一部として提供する方式。

```text
supported = True
native = True
```

モデルが `tool_use` / tool call で操作を返し、ランタイムが操作を実行してスクリーンショットを `tool_result` として返す。

### UAG 側 Computer Tool

モデル自体はネイティブ CUA を持たないが、通常のツール呼び出しとスクリーンショットを組み合わせて UAG が操作を提供する方式。

```text
supported = True
native = False
```

この方式は Qwen やローカルモデルなどに適用できる可能性があるが、モデルとランタイムの組み合わせとして明示的に対応させる。ネイティブ CUA を通常の JSON Function Tool に暗黙変換する設計は避ける。

## 5. 問い合わせ API

```python
def supports_computer_use(
    model_name: str,
    provider: str | None = None,
) -> bool: ...


def get_computer_use_capability(
    model_name: str,
    provider: str | None = None,
) -> ComputerUseCapability | None: ...


def supports_computer_action(
    model_name: str,
    action: str,
    provider: str | None = None,
) -> bool: ...


def supports_computer_environment(
    model_name: str,
    environment: str,
    provider: str | None = None,
) -> bool: ...
```

### 5.1 ルックアップ優先順位

1. `provider + exact model`
2. `provider + 正規化済みモデル名`
3. `provider + model family/version`
4. `provider default`
5. `unknown`

プロバイダー別名は正規化する。ただし Google API と Vertex など、API 条件が異なる場合はバックエンドの違いを保持する。モデルバージョン、ツールバージョン、API バージョン、ベータヘッダーのバージョンは別フィールドで扱う。

未知のモデル名を文字列部分一致だけで対応済みと推測しない。確証がなければ `None` または `supported=False` とする。

## 6. プロバイダー登録の考え方

共有会話では Anthropic、OpenAI、Gemini、Qwen/UAG が例として挙げられている。ただし、モデル名や API 名には将来仕様・暫定名称・会話内の不整合が含まれるため、下表は実装候補であって確定仕様ではない。

| 系統 | 方式 | 登録時の注意 |
|---|---|---|
| Anthropic | ネイティブ Computer Tool | `computer_20250124` / `computer_20251124` のような tool version、対応モデル、ベータヘッダーをモデル単位で管理する |
| OpenAI | ネイティブ Computer Use | `computer-use-preview` や `computer` など、実際の API で使用する識別子を公式仕様で確認する |
| Gemini | ネイティブまたはプレビュー機能 | `gemini_computer_use` 等の名称、Browser/Desktop/Mobile の対応範囲、提供チャネルを確認する |
| Qwen / ローカル | UAG Computer Tool | `native=False` とし、UAG ランタイム、アクセシビリティ API、画面取得方式を別途登録する |

### 6.1 Anthropic の実装候補

共有会話では、次のようなネイティブツール payload が例示されている。

```python
{
    "type": "computer_20251124",
    "name": "computer",
    "display_width_px": 1920,
    "display_height_px": 1080,
    "display_number": 1,
    "enable_zoom": True,
}
```

また、ベータヘッダーとして `computer-use-2025-11-24` が例示されている。いずれも利用前に公式 API 仕様と対象モデルを照合する。

## 7. 実行アーキテクチャ

```text
llmcapa
  └─ capability discovery
       ├─ native provider adapter
       │    ├─ ClaudeComputerAdapter
       │    ├─ OpenAIComputerAdapter
       │    └─ GeminiComputerAdapter
       └─ UAG Computer Tool adapter
            └─ Computer Runtime
                 ├─ Windows
                 ├─ macOS
                 └─ Linux
```

### 7.1 正規化ランタイムインターフェース

```python
class ComputerRuntime:
    def screenshot(self): ...
    def click(self, x: int, y: int, button: str = "left"): ...
    def double_click(self, x: int, y: int): ...
    def move(self, x: int, y: int): ...
    def type_text(self, text: str): ...
    def key(self, key: str): ...
    def scroll(self, x: int, y: int, dx: int, dy: int): ...
    def drag(self, x1: int, y1: int, x2: int, y2: int): ...
    def wait(self, seconds: float): ...
```

座標操作だけに依存せず、可能な範囲で UI Accessibility / Automation API も併用する。DPI スケーリング、解像度、ポップアップ、フォーカス、画面外座標などをランタイム側で吸収する。

## 8. uag への組み込み方

### 8.1 ネイティブ Computer Tool を通常ツール登録に混ぜない

`computer_20251124` のようなネイティブツールは、通常の JSON Schema Function Tool とは形式が異なる可能性がある。そのため、既存の `tools.get_tool_specs()` に普通のツールとして登録するのではなく、プロバイダーアダプターでネイティブ payload として追加する。

候補ファイル:

```text
src/uagent/providers/claude_computer.py
src/uagent/providers/llm_claude.py
src/uagent/llm_round_helpers.py
tests/test_claude_computer.py
```

実際のリポジトリ構成に合わせて配置を調整する。

### 8.2 Computer Use のターンループ

通常の関数呼び出しとは別に、次のループを実装する。

```text
モデル: tool_use / computer action
  ↓
プロバイダーアダプター: 正規化アクションへ変換
  ↓
Computer Runtime: クリック、入力、スクロールなどを実行
  ↓
Runtime: スクリーンショットを取得
  ↓
プロバイダーアダプター: tool_result に変換
  ↓
モデルへ再送
```

アクション変換、スクリーンショット形式、エラー、タイムアウト、最大ループ回数をアダプターごとにテストする。

### 8.3 自動アダプター選択

```python
cap = get_computer_use_capability(model_name, provider)

if cap is None or not cap.supported:
    raise UnsupportedCapability("computer use is not supported")

if cap.native:
    adapter = provider_registry.native_adapter(cap.provider)
else:
    adapter = uag_computer_adapter
```

ネイティブ機能が利用できない場合に、明示的に UAG Computer Tool が登録されているときだけフォールバックする。暗黙の変換や、対応していないモデルへのサイレント実行は行わない。

## 9. セキュリティと権限

Capability は「モデル/API が機能を持つか」を示すだけであり、実行許可ではない。ランタイム側に以下の独立した制御を設ける。

- `computer_use_enabled`
- 対象アプリケーション、ウィンドウ、ドメインの allowlist
- sandbox / remote desktop
- ファイルシステム、ネットワーク、クリップボードの制限
- ユーザー確認が必要なアクション
- 操作ログ、スクリーンショット保存ポリシー、保持期間
- 最大操作回数、最大実行時間、失敗時の停止

原則として、次の操作は明示確認を要求する。

- ファイル削除、シェル実行
- パスワード・API キーなどの資格情報入力
- 購入、送信、フォーム送信
- メッセージ送信、メール送信
- ログアウト、アカウント・権限変更
- 外部サービスへの不可逆な更新

Web ページ、PDF、メール、チャット、画面上の文字列にはプロンプトインジェクションが含まれる可能性がある。画面上の指示を権限付与やユーザー承認とみなさず、ランタイムを分離して検証する。

## 10. テスト項目

### capability 層

- プロバイダーとモデルの組み合わせ
- 完全一致、正規化名、モデルファミリー、未知モデル
- `supported` / `native` の組み合わせ
- `ga`、`beta`、`preview`、`legacy`、`deprecated`、`retired`
- `computer_20250124`、`computer_20251124` などの tool version
- `zoom` を含むアクション差異
- desktop / browser / mobile の環境差異
- ベータヘッダーと source URL の保持

### adapter/runtime 層

- tool payload の生成
- action の正規化と逆変換
- スクリーンショットの tool result 化
- API エラー、未対応アクション、タイムアウト
- DPI、複数ディスプレイ、フォーカス、ポップアップ
- 最大ターン数と安全停止
- 実ランタイムを使わない dry-run / mock テスト

## 11. 段階的な実装計画

1. `ComputerUseCapability` の基本フィールドを追加
2. `environments` と `actions` を追加
3. capability レジストリとルックアップ優先順位を実装
4. Anthropic のネイティブアダプターを実装
5. Computer Use ターンループとスクリーンショット返却を実装
6. OpenAI、Gemini のアダプターを公式仕様に合わせて追加
7. UAG Computer Runtime と非ネイティブアダプターを追加
8. capability に基づく自動アダプター選択を追加
9. 権限確認、allowlist、監査ログを追加
10. 公式仕様の定期更新と capability の有効期限・検証日を管理

## 12. 未確定事項

- 各プロバイダーの正式な tool type、API endpoint、モデル対応表
- Computer Tool のバージョンとモデルバージョンの対応
- Gemini の提供環境・提供チャネル
- OpenAI の現行 Computer Use 識別子
- UAG Computer Tool の OS 対応範囲とアクセシビリティバックエンド
- スクリーンショットの解像度、圧縮、PII マスキング
- 実行承認 UI、監査ログ、再現用アーティファクトの保存仕様

## 13. まとめ

llmcapa では Computer Use を単一の真偽値ではなく、次の三層に分けて扱うのが適切である。

1. **Capability**: モデル/API が何をサポートするか
2. **Adapter**: プロバイダー固有の tool call を正規化する方法
3. **Runtime**: 実際に画面・マウス・キーボードを操作する実行環境

この分離により、ネイティブ CUA と UAG 側ツールを同じ問い合わせ API から扱いつつ、API 仕様の差異、モデルごとのバージョン差異、セキュリティ権限を独立して管理できる。


## 14. llmcapa 自体の既存互換性

Computer Use 対応は、既存の llmcapa のデータ形式・公開 API・モデル定義を置き換えるのではなく、**追加の capability namespace として導入する**。

### 14.1 既存モデル定義への追加

既存定義は維持し、`computer_use` をオプション項目として追加する。

```json
{
  "provider": "anthropic",
  "model": "claude-sonnet",
  "supports_reasoning": true,
  "max_tokens": 200000,
  "computer_use": {
    "supported": true,
    "native": true,
    "tool_type": "computer",
    "tool_version": "..."
  }
}
```

既存の利用側が追加フィールドを無視できる構造であれば、従来のモデル判定やプロバイダー処理は変更せずに動作する。

### 14.2 既存 API を維持する

既存の API の戻り値型や基本構造は変更しない。Computer Use 専用の問い合わせ API を追加する。

```python
def supports_computer_use(provider: str, model: str) -> bool: ...

def get_computer_use_capability(
    provider: str,
    model: str,
) -> ComputerUseCapability | None: ...
```

既存 API の戻り値を突然 `ComputerUseCapability` に置き換えたり、既存のモデル定義へ新しい必須フィールドを追加したりしない。

### 14.3 未登録・非対応・対応済みを区別する

`computer_use` が存在しない状態と、非対応であることが確認済みの状態は区別する。

```text
None / 未登録       = 情報なし・未確認
supported=False     = 対応していないと確認済み
supported=True      = 対応している
```

問い合わせ API の単純な真偽値関数では、未登録を安全側に倒して `False` として返してよい。一方、詳細 API では `None` を保持し、情報不足を隠さない。

### 14.4 後方互換になる変更

- 既存モデル定義へのオプションフィールド追加
- 新しい capability タイプの追加
- 新しい status 値の追加
- 未知フィールドの無視
- 既存モデルへのデフォルト値適用
- Computer Use 専用 API の追加

### 14.5 互換性を壊す変更

- 既存フィールドの名前や型を変更する
- 既存の必須フィールドを増やす
- `computer_use` を全モデル定義の必須項目にする
- 既存 API の戻り値型を変更する
- 未知の `tool_type` や `status` を即座にエラーにする
- 既存の JSON/YAML 定義を新形式へ強制変換する

### 14.6 スキーマバージョン

Computer Use の追加だけであれば、メジャーバージョンを上げず、後方互換の拡張として導入できる。

```json
{
  "schema_version": "1.x",
  "capabilities": {
    "computer_use": {
      "supported": true
    }
  }
}
```

既存フィールドの型変更、既存項目の削除、必須項目化を行う場合は、`2.x` などのメジャーバージョンを検討する。

### 14.7 llmcapa における推奨構造

```text
既存の llmcapa capability
└── computer_use: optional capability
      ├── supported
      ├── native
      ├── tool_type
      ├── tool_version
      ├── environments
      └── actions
```

この構造なら、Computer Use に対応していない既存モデル、Computer Use 情報を持たない古い定義、既存の llmcapa 利用コードを維持したまま、詳細な Computer Use capability を段階的に追加できる。
