# Azure AI Catalog API

Azure AI Foundry の Model Catalog は内部 API を通じてモデルデータを提供しています。
この API を使用すると、カタログに掲載されている全モデルの情報（context window、
推論タスク、プロバイダ、価格情報など）をプログラムで取得できます。

## エンドポイント

```
POST https://ai.azure.com/api/{region}/asset-gallery/v1.0/models
```

`{region}` は Azure リージョン（例: `japaneast`）。ログインユーザーのリージョンに依存します。

## 認証

この API を使用するには、`https://ai.azure.com/catalog/models` にブラウザで
アクセスした際に発行されるセッション認証が必要です。Playwright などの
ブラウザ自動化ツールを使用してページにアクセスした後、同じセッション内で
操作する必要があります。

**重要**: 同一セッション内であっても、`page.evaluate()` 経由の `fetch()` では
API は動作しません（400エラー）。理由は不明ですが、ブラウザの「Next」ボタン
クリックによる実際の DOM 操作のみが API を正しく呼び出せます。

## ページネーション（SSR + API）

Azure AI Catalog のページネーションは特殊で、2段階になっています。

| 段階 | 方法 | データソース |
|------|------|-------------|
| **1ページ目**（人気上位51モデル） | SSR（HTML に直接埋め込み） | サーバーサイドレンダリング |
| **2ページ目以降** | 「Next」ボタンクリック | `asset-gallery/v1.0/models` API |

### SSR 1ページ目の問題

カタログの **1ページ目**（人気順で最初の51モデル）は **SSR（Server-Side Rendering）**
で HTML に直接埋め込まれており、API では取得できません。
そのため、API ベースの全件取得では **1ページ目のモデルが欠落** します。

該当するモデルの例:

```
gpt-5.6-sol, gpt-5.6-luna, gpt-5.6-terra
gpt-realtime-2.1, gpt-chat-latest
Kimi-K2.7-Code, claude-sonnet-5
Cohere-command-a-plus-05-2026
...
```

### API の continuationToken の制約

API の呼び出しには SSR ページから生成された `continuationToken` が必要です。
このトークンなしでは API はデータを返しません。具体的には:

1. ページロード → SSR で1ページ目表示（51モデル）
2. 「Next」クリック → SSR 状態から生成された continuationToken 付きで API 呼び出し
3. API → 2ページ目のデータ + 新しい continuationToken を返す
4. 以下繰り返し

そのため、API 単体で先頭ページから全件取得することはできません。

## スクレイピングの実装方式（Playwright）

上記の制約から、唯一動作する方法は Playwright でブラウザを操作し、
「Next」ボタンをクリックし続けて各ページの API レスポンスを横取りする方式です。

### 動作手順

1. `https://ai.azure.com/catalog/models` にアクセス
2. SSR の DOM から1ページ目のモデル名を取得
3. 「Next」ボタンを繰り返しクリック
4. 各クリック後に API レスポンスをキャプチャ
5. API で取得したモデル + SSR のみのモデル（両方に現れないもの）を統合
6. SSR のみのモデルは詳細ページを個別訪問してメタデータを取得

### 実装のポイント

```python
# SSR 1ページ目のモデル名を DOM から取得
ssr_names = await page.evaluate("""
    () => {
        const links = document.querySelectorAll('a[class*="_cardLink"]');
        return Array.from(links).map(a => {
            const href = a.href || '';
            return href.replace(/\\/$/, '').split('/').pop();
        }).filter(n => n);
    }
""")

# 「Next」を繰り返しクリック（これが唯一の API 呼び出し方法）
while True:
    next_btn = page.locator('button:has-text("Next")')
    if await next_btn.is_disabled():
        break

    # API レスポンスを横取り
    future = asyncio.get_event_loop().create_future()
    def capture(response):
        if "asset-gallery" in response.url and response.status == 200:
            future.set_result(response)
    page.on("response", capture)

    await next_btn.click()
    resp = await asyncio.wait_for(future, timeout=10)
    data = await resp.json()
    # data["value"] に2ページ目以降のモデルが含まれる
```

### スクリプト

実際の実装は `scripts/_scrape_azure_catalog.py` を参照してください。

```
python scripts/_scrape_azure_catalog.py --save
```

## 参考: API のリクエスト形式

### フィルター一覧

| フィールド | 演算子 | 値 | 説明 |
|-----------|--------|-----|------|
| `type` | `eq` | `["models"]` | モデル種別 |
| `kind` | `eq` | `["Versioned"]` | バージョン管理 |
| `properties/isAnonymous` | `ne` | `["true"]` | 匿名モデルを除外 |
| `annotations/archived` | `ne` | `["true"]` | アーカイブを除外 |
| `properties/userProperties/is-promptflow` | `notexists` | - | PromptFlow を除外 |
| `labels` | `eq` | `["latest"]` | 最新ラベルのみ |

### リクエスト例（「Next」クリック時に実際に送信される内容）

```json
{
  "filters": [
    {"field": "type", "operator": "eq", "values": ["models"]},
    {"field": "kind", "operator": "eq", "values": ["Versioned"]},
    {"field": "properties/isAnonymous", "operator": "ne", "values": ["true"]},
    {"field": "annotations/archived", "operator": "ne", "values": ["true"]},
    {"field": "properties/userProperties/is-promptflow", "operator": "notexists"},
    {"field": "labels", "operator": "eq", "values": ["latest"]}
  ],
  "searchParameters": {
    "freeTextSearch": "",
    "freeTextSearchColumns": [
      {"name": "annotations/systemCatalogData/publisher"},
      {"name": "properties/name"},
      {"name": "annotations/systemCatalogData/inferenceTasks"}
    ]
  },
  "order": [{"field": "usage/popularity", "direction": "Desc"}],
  "pageSize": 51,
  "facets": [],
  "includeTotalResultCount": true,
  "searchBuilder": "AppendPrefix",
  "continuationToken": "base64_encoded_token..."
}
```

### レスポンス例

```json
{
  "totalCount": 1723,
  "value": [
    {
      "annotations": {
        "systemCatalogData": {
          "publisher": "OpenAI",
          "displayName": "GPT-4o",
          "textContextWindow": 128000,
          "maxOutputTokens": 16384,
          "inferenceTasks": ["Chat completion", "Responses"],
          "inputModalities": ["text", "image"],
          "outputModalities": ["text"],
          "modelCapabilities": {...}
        }
      },
      "properties": {
        "name": "gpt-4o",
        ...
      }
    }
  ],
  "continuationToken": "base64_encoded_token..."
}
```

## データソース全体の構成

各プロバイダのデータソースと SSR リスクの詳細は `docs/catalog_data_sources.md` を参照してください。
