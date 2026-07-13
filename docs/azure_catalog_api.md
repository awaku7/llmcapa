# Azure AI Catalog API

Azure AI Foundry の Model Catalog は内部 API を通じてモデルデータを提供しています。
この API を使用すると、カタログに掲載されている全モデルの情報（context window、
推論タスク、プロバイダ、価格情報など）をプログラムで取得できます。

## エンドポイント

```
POST https://ai.azure.com/api/{region}/asset-gallery/v1.0/models
```

`{region}` は Azure リージョン（例: `japanwest`, `japaneast`）。

## 認証

この API を使用するには、`https://ai.azure.com/catalog/models` にブラウザで
アクセスした際に発行される認証クッキーが必要です。Playwright などの
ブラウザ自動化ツールを使用してページにアクセスした後、同じセッション内で
API を呼び出すことで認証情報が自動的に付与されます。

直接 `fetch` や `urllib` で呼び出すことはできません（認証が必要）。

## リクエスト形式

### 必須パラメータ

| パラメータ | 型 | 説明 |
|-----------|-----|------|
| `filters` | array | 検索フィルター |
| `searchParameters` | object | 検索パラメータ |
| `order` | array | ソート順 |
| `pageSize` | int | 1ページあたりの件数（最大200程度） |
| `includeTotalResultCount` | bool | 総件数を返すか |
| `searchBuilder` | string | `"AppendPrefix"` 固定 |

### フィルター一覧

| フィールド | 演算子 | 値 | 説明 |
|-----------|--------|-----|------|
| `type` | `eq` | `["models"]` | モデル種別 |
| `kind` | `eq` | `["Versioned"]` | バージョン管理 |
| `properties/isAnonymous` | `ne` | `["true"]` | 匿名モデルを除外 |
| `annotations/archived` | `ne` | `["true"]` | アーカイブを除外 |
| `properties/userProperties/is-promptflow` | `notexists` | - | PromptFlow を除外 |
| `labels` | `eq` | `["latest"]` | 最新ラベルのみ |

### ページネーション

初回リクエストでは `continuationToken` を送信しません。
レスポンスに含まれる `continuationToken` を次のリクエストのボディに含めます。
トークンが `null` または空の場合は最終ページです。

### リクエスト例

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
  "pageSize": 200,
  "facets": [],
  "includeTotalResultCount": true,
  "searchBuilder": "AppendPrefix"
}
```

## レスポンス形式

```json
{
  "totalCount": 1723,
  "value": [
    {
      "relevancyScore": 1.0,
      "entityResourceName": "...",
      "schemaId": "...",
      "entityId": "...",
      "kind": "Versioned",
      "annotations": {
        "name": "...",
        "description": "...",
        "labels": ["latest"],
        "stage": "...",
        "systemCatalogData": {
          "publisher": "OpenAI",
          "displayName": "GPT-4o",
          "textContextWindow": 128000,
          "maxOutputTokens": 16384,
          "maxInputTokens": 130000,
          "inferenceTasks": ["Chat completion", "Responses"],
          "inputModalities": ["text", "image"],
          "outputModalities": ["text"],
          "modelCapabilities": {...},
          "deploymentTypes": [...],
          "license": "...",
          "summary": "..."
        }
      },
      "properties": {
        "name": "gpt-4o",
        "id": "...",
        "version": "...",
        ...
      }
    }
  ],
  "continuationToken": "base64_encoded_token..."
}
```

### 主要フィールド

| フィールドパス | 説明 |
|--------------|------|
| `properties.name` | モデルID |
| `annotations.systemCatalogData.publisher` | プロバイダ名 |
| `annotations.systemCatalogData.displayName` | 表示名 |
| `annotations.systemCatalogData.textContextWindow` | コンテキストウィンドウサイズ |
| `annotations.systemCatalogData.maxOutputTokens` | 最大出力トークン数 |
| `annotations.systemCatalogData.maxInputTokens` | 最大入力トークン数 |
| `annotations.systemCatalogData.inferenceTasks` | 推論タスク一覧 |
| `annotations.systemCatalogData.inputModalities` | 入力モダリティ |
| `annotations.systemCatalogData.outputModalities` | 出力モダリティ |
| `annotations.systemCatalogData.modelCapabilities` | モデル機能（function calling 等） |
| `annotations.systemCatalogData.deploymentTypes` | デプロイ種別 |
| `annotations.systemCatalogData.license` | ライセンス |
| `annotations.systemCatalogData.summary` | モデル概要 |

## プロバイダ別モデル数（実測値）

| プロバイダ | モデル数 |
|-----------|---------|
| Hugging Face / HuggingFace | 1154 |
| Microsoft / OpenAI | 129 |
| Meta | 42 |
| Nvidia | 36 |
| Fireworks | 24 |
| Mistral AI | 18 |
| その他 | 約269 |
| **合計** | **1672** |

※ カタログ表示上の「3543」は Hugging Face の全バリアントを含む数値。
API では `labels=latest` フィルタで重複を除外した 1672 モデルが取得可能。

## 実装例（Playwright + Python）

```python
import asyncio
import json
from playwright.async_api import async_playwright

async def fetch_azure_catalog(page, region="japanwest", page_size=200):
    """Fetch all models from Azure AI Catalog via internal API."""
    base_url = f"https://ai.azure.com/api/{region}/asset-gallery/v1.0/models"
    
    request_body = {
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
        "pageSize": page_size,
        "facets": [],
        "includeTotalResultCount": True,
        "searchBuilder": "AppendPrefix"
    }
    
    all_models = []
    token = None
    
    while True:
        body = dict(request_body)
        if token:
            body["continuationToken"] = token
        
        result = await page.evaluate(f"""
            async () => {{
                const resp = await fetch('{base_url}', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({json.dumps(body)})
                }});
                return await resp.json();
            }}
        """)
        
        values = result.get('value', [])
        all_models.extend(values)
        
        token = result.get('continuationToken')
        if not token:
            break
    
    return all_models
```
