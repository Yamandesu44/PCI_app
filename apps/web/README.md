# @pci/web — 展開予想フロントエンド

Next.js（App Router）+ TypeScript。`@pci/api-client` 経由で FastAPI の
展開予想を取得し、**PCI を知らない競馬ファンでも展開を理解できる UI** で表示する
（コアバリュー）。RPCI・PAI といった専門用語は、色・バー・自然文に翻訳する。

## セットアップ

```bash
# モノレポルートで一括インストール（npm workspaces）
npm install

cd apps/web
cp .env.example .env.local   # API_BASE_URL を設定
```

## 開発

```bash
npm run dev        # http://localhost:3000
npm run build      # 本番ビルド（型チェック込み）
npm run typecheck  # tsc --noEmit
npm run test       # vitest（純粋プレゼンテーションロジック）
```

表示には FastAPI バックエンドの起動が必要（`API_BASE_URL`）。
ローカル開発では認証環境変数を設定しない。

## 主要ルート

| ルート | 内容 |
|---|---|
| `/` | トップ（出走前=展開予想 / 確定後=ペース分析への導線） |
| `/forecast-review` | 保存済みの事前予想と実際の展開を比較する検証画面 |
| `/races/{raceKey}/forecast` | 展開予想（想定展開・統合上位・注意馬・隊列・やさしい解説・根拠） |
| `/races/{raceKey}/pace-analysis` | 確定後ペース分析（各馬PCI・実績RPCI・PCI3、★=PCI3寄与馬・回顧コメント） |

未登録レース・出走馬未確定（forecast）／未確定レース（pace-analysis）は 404（`not-found.tsx`）。

## 配備

Vercel を使用。モノレポルートの `vercel.json` にビルド設定済み:

- **installCommand**: `npm ci`（モノレポルートで全 workspace をインストール）
- **buildCommand**: `npm run build -w @pci/web`
- **outputDirectory**: `apps/web/.next`

Vercel プロジェクト設定で必要な環境変数:

| キー | 説明 |
|---|---|
| `API_BASE_URL` | FastAPI バックエンドの URL（例: `https://pci-api.railway.app`）|
| `API_ACCESS_TOKEN` | FastAPIの`PUBLIC_API_TOKEN`と同じサーバー間トークン |
| `BETA_ACCESS_USER` | 少人数テスト用の共有ユーザー名 |
| `BETA_ACCESS_PASSWORD` | 少人数テスト用の長い共有パスワード |

詳細: [`docs/design/08-deployment.md`](../../docs/design/08-deployment.md)

少人数ロケテストでも、WebとAPIをアクセス制限なしで公開しないこと。開始条件と点検手順は
[`docs/LOCATION_TEST.md`](../../docs/LOCATION_TEST.md)を参照。
