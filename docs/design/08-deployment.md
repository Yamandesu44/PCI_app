# 08. デプロイ構成

> **現状の注意:** 以下は構成候補であり、そのまま一般公開できる完成済み手順ではない。
> 個別ユーザー認証は未実装。少人数用の共有認証を有効にし、
> [`../LOCATION_TEST.md`](../LOCATION_TEST.md)の開始条件とアクセス制限を満たしてから行う。

## アーキテクチャ

```
┌──────────────────────────────────────────────────────────┐
│  Vercel (フロントエンド)                                   │
│  apps/web — Next.js App Router                          │
│  環境変数: API_BASE_URL                                   │
└───────────────────────┬──────────────────────────────────┘
                        │ HTTPS REST
┌───────────────────────▼──────────────────────────────────┐
│  Railway / Render / Fly.io (バックエンド)                 │
│  apps/api — FastAPI + Uvicorn                           │
│  環境変数: DATABASE_URL                                   │
└───────────────────────┬──────────────────────────────────┘
                        │ psycopg3
┌───────────────────────▼──────────────────────────────────┐
│  マネージド PostgreSQL                                    │
│  (Railway PostgreSQL / Supabase / Neon など)             │
└──────────────────────────────────────────────────────────┘
```

---

## 1. フロントエンド — Vercel

### セットアップ手順

1. Vercel ダッシュボードで **New Project** → リポジトリを選択
2. **Framework Preset** は `Next.js` が自動検出されるが、`vercel.json` が既に設定済みのため上書き不要
3. **Root Directory** は空白（= リポジトリルート）のまま
4. **環境変数** を追加:

| キー | 値 | スコープ |
|---|---|---|
| `API_BASE_URL` | FastAPI バックエンドの URL（例: `https://pci-api.railway.app`）| Production / Preview |
| `API_ACCESS_TOKEN` | FastAPIの`PUBLIC_API_TOKEN`と同じサーバー間トークン | Production / Preview |
| `BETA_ACCESS_USER` | 少人数テスト用の共有ユーザー名 | Production / Preview |
| `BETA_ACCESS_PASSWORD` | 少人数テスト用の長い共有パスワード | Production / Preview |

5. **Deploy** ボタンを押す

### `vercel.json` の仕組み

```json
{
  "installCommand": "npm ci",         // モノレポルートで全 workspace をインストール
  "buildCommand":   "npm run build -w @pci/web",  // apps/web で next build
  "outputDirectory": "apps/web/.next",            // ビルド出力先
  "env": { "API_BASE_URL": "@api_base_url" }      // Vercel の秘密参照
}
```

`@api_base_url` は Vercel の **Environment Variables** ストアに登録した値を参照する。
登録コマンド（Vercel CLI が必要）:

```bash
vercel env add API_BASE_URL production
# プロンプトで FastAPI バックエンドの URL を入力
```

### CI との関係

GitHub 連携を設定すると Vercel が自動デプロイを行う。
ローカル品質チェックは `.github/workflows/ci-web.yml` で先行して実行される:

```
push → CI (typecheck + vitest + next build) → Vercel デプロイ
```

---

## 2. バックエンド — Railway（推奨）

FastAPI は Vercel のサーバレス環境では動作しない（長命プロセス・DB コネクション）。
Railway はコンテナベースで Python 対応が容易なため推奨。

### セットアップ手順

1. [railway.app](https://railway.app) でプロジェクト作成
2. GitHub リポジトリを連携
3. **Service → Source** で `apps/api` ディレクトリを選択
4. Railway が `Procfile` を検出し、以下のコマンドで起動:
   ```
   uvicorn pci.presentation.app:app --host 0.0.0.0 --port $PORT
   ```
5. 同一プロジェクト内に **PostgreSQL サービス** を追加
6. Railway が `DATABASE_URL` を自動設定するため、環境変数を確認

### 環境変数

| キー | 値 | 設定先 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://<user>:<pass>@<host>:5432/<db>` | Railway → Variables |
| `PUBLIC_API_TOKEN` | Webの`API_ACCESS_TOKEN`と同じサーバー間トークン | Railway → Variables |
| `INGEST_TOKEN` | Windows取り込み専用の別トークン | Railway → Variables |

### マイグレーション

デプロイ後にマイグレーションを実行:

```bash
# Railway CLI または SSH 接続で:
cd apps/api && alembic upgrade head
```

または Railway のカスタムスタートコマンドに前置きとして追加:

```
alembic upgrade head && uvicorn pci.presentation.app:app --host 0.0.0.0 --port $PORT
```

---

## 3. 代替バックエンドサービス

| サービス | 対応ファイル | 備考 |
|---|---|---|
| **Railway** | `apps/api/Procfile` | 推奨。PostgreSQL 同梱。 |
| **Render** | `apps/api/Procfile` | 無料 tier あり（スリープ注意）|
| **Fly.io** | `fly.toml`（別途作成） | 低レイテンシ重視の場合 |
| **Docker** | `docker-compose.yml` | セルフホスト / VPS |

---

## 4. セキュリティチェックリスト

- [ ] `.env` ファイルがコミットに含まれていない（`.gitignore` 確認）
- [ ] JV-Link SID 等の認証情報が Vercel / Railway の変数ストアにのみ存在する
- [ ] `DATABASE_URL` にパスワードがハードコードされていない
- [ ] `ANTHROPIC_API_KEY`（将来追加時）を環境変数で管理し、コードに含めない
- [ ] 公開するのは独自指標・分析結果（PAI/PCI/コメント等）のみ
- [ ] WebとAPIの両方を招待者だけに制限している
- [ ] Webの共有認証とAPIのBearer認証をHTTPレベルで確認した
- [ ] `/internal/ingest/*`の`INGEST_TOKEN`を本番で必須にしている
- [ ] FastAPIの管理用・内部用経路を無制限にインターネット公開していない

---

## 5. ローカル E2E 確認（デプロイ前）

```bash
# 1. バックエンド起動
cd apps/api
docker-compose -f ../../docker-compose.yml up -d db
uvicorn pci.presentation.app:app --reload

# 2. フロントエンド起動
cd apps/web
API_BASE_URL=http://127.0.0.1:8000 npm run dev

# 3. http://localhost:3000 で動作確認
```
