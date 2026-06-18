# @pci/api-client — 型共有クライアント

FastAPI が生成する OpenAPI スペックから TypeScript 型を生成し、
バックエンドとフロントエンド（`apps/web`）の型を一致させる（設計書 04 §4）。

```
FastAPI → openapi.json → openapi-typescript → schema.d.ts → apps/web で import
```

## 型の再生成

```bash
# 1. API から openapi.json を更新（FastAPI を真実の源とする）
cd apps/api && python scripts/export_openapi.py

# 2. openapi.json → TypeScript 型
cd packages/api-client && npm run generate
npm run typecheck
```

`openapi.json` は `apps/api` の契約テスト（`test_openapi_snapshot.py`）で
コードとの同期を検証しており、ドリフトは CI で検知される（設計書 04 §5）。

## 使い方

```ts
import { createClient, type Forecast } from "@pci/api-client";

const api = createClient({ baseUrl: process.env.API_BASE_URL! });
const forecast: Forecast = await api.getForecast("2026062005010101");
```

公開しているのは独自指標・分析結果（想定RPCI・PAI・展開シナリオ・根拠）のみで、
生データは含まない（C2）。
