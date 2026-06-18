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

## 主要ルート

| ルート | 内容 |
|---|---|
| `/` | トップ（サンプルレースへの導線） |
| `/races/{raceKey}/forecast` | 展開予想（想定ペース・展開を作る馬・展開が向く馬の PAI・根拠） |

未登録レース・出走馬未確定は 404（`not-found.tsx`）。

## 配備

Vercel を想定（`apps/web` をルートに指定）。`API_BASE_URL` は Vercel の
環境変数で設定し、生データ・認証情報はコードに含めない。
