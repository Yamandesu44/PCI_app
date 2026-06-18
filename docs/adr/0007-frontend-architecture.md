# ADR-0007: フロントエンド構成（Next.js App Router + OpenAPI 型共有）

- **Status:** Accepted
- **Date:** 2026-06-18
- **Deciders:** @yamandesu44

---

## Context

MVP 公開には、FastAPI の展開予想を消費する Web フロントエンドが必要（設計書 05 S5）。
本プロダクトのコアバリューは「PCI を理解していない競馬ファンでも展開予想を活用できる」
ことであり、UI が価値実現の中心になる。以下を満たしたい:

- バックエンド（Python）とフロント（TypeScript）の**型を一致**させ、契約のズレを CI で検知（設計書 04 §4/§5）
- **生データを露出しない**（C2）。独自指標・分析結果（想定RPCI・PAI・展開シナリオ・根拠）のみ表示
- Vercel への配備（アーキテクチャ地図）
- モノレポ（ADR-0003）の一部として `apps/web` / `packages/api-client` を配置

---

## Decision

### 1. フレームワーク: Next.js（App Router）+ React Server Components

- 予想ページはサーバコンポーネントでバックエンドへ問い合わせ、`API_BASE_URL` を
  サーバ側に隠蔽する（生データ・接続情報をクライアントへ出さない）
- `force-dynamic` で実行時フェッチとし、ビルド時にバックエンドへ依存しない

### 2. 型共有: FastAPI → OpenAPI → openapi-typescript

```
FastAPI → scripts/export_openapi.py → packages/api-client/openapi.json
        → openapi-typescript → schema.d.ts → apps/web で import
```

- `openapi.json` は契約テスト（`test_openapi_snapshot.py`）でコードとの同期を保証
- `packages/api-client` は型生成のドリフトを Web CI（`git diff --exit-code`）で検知

### 3. パッケージ管理: npm workspaces（ADR-0003 のモノレポに沿う）

- `@pci/api-client` を TypeScript ソースで配布し、Next の `transpilePackages` で取り込む
- ビルド成果物の中間管理を避け、単一の型ソースを共有

### 4. プレゼンテーション層の分離とテスト

- 専門用語→非専門家向け表現の変換（色・バー・自然文）は純粋関数 `lib/pace.ts` に隔離し
  vitest で単体テスト（説明可能性・コアバリューの中核ロジック）
- レンダリングの妥当性は `next build`（型チェック込み）で担保

---

## Consequences

**ポジティブ:**
- バック/フロントの型不一致をコミット時・CI で検知でき、破壊的変更が可視化される
- 生データ非公開（C2）をサーバコンポーネント境界で構造的に担保
- 予測戦略やスキーマが変わっても、型生成フローが差分を自動反映

**ネガティブ:**
- OpenAPI → 型の再生成フロー（2 ステップ）を運用で守る必要がある
- Next.js / React のバージョン追従コストが発生する

**緩和策:**
- 型ドリフトは CI で強制（Web CI の `generate + git diff`、API の snapshot 契約テスト）
- 生成手順は各 README と CLAUDE.md 頻用コマンドに明記
