# PCI App — 競馬展開予想 SaaS

JRA-VAN DataLab の JV-Link から取得した競馬データを元に、レース展開（ペース・脚質適性）を
自動分析する SaaS アプリ。

> **コアバリュー:** 「PCI を理解していない競馬ファンでも展開予想を活用できること」
>
> TARGET の完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
> **説明可能なアルゴリズム**に変換することが目的。

---

## 現在のステータス

**MVP 実装中（fixtures ベースで価値検証）。**

| 領域 | 状態 |
|---|---|
| ドメイン核（PCI / 脚質 / 想定RPCI / PAI / 展開シナリオ） | ✅ 実装済み・テスト済み |
| アプリケーション層（ユースケース） | ✅ 実装済み |
| DB（core / mart）+ Alembic + Repository | ✅ 実装済み（mart 永続化込み） |
| FastAPI（`/forecast`・レース詳細） | ✅ 実装済み |
| 型共有（`packages/api-client`） | ✅ OpenAPI → TypeScript 生成 |
| フロントエンド（`apps/web` / Next.js） | ✅ 展開予想ページ（`vercel.json` 配備設定済み） |
| ingestion-worker（JV-Link 実データ） | ⏳ fixtures のみ（Windows 実装は後続） |

ローカル起動: API は [`apps/api/README.md`](./apps/api/README.md)、Web は [`apps/web/README.md`](./apps/web/README.md) を参照。

---

## ドキュメント

| 種別 | 場所 |
|---|---|
| プロジェクト指針（必読） | [`CLAUDE.md`](./CLAUDE.md) |
| ユビキタス言語 | [`docs/domain/ubiquitous-language.md`](./docs/domain/ubiquitous-language.md) |
| 設計書 | [`docs/design/`](./docs/design/) |
| ADR（意思決定記録） | [`docs/adr/`](./docs/adr/) |

### 設計書（docs/design/）
1. [要求整理](./docs/design/01-requirements.md)
2. [DDDドメインモデル](./docs/design/02-domain-model.md)
3. [データモデル設計](./docs/design/03-data-model.md)
4. [API設計](./docs/design/04-api-design.md)
5. [開発ロードマップ](./docs/design/05-roadmap.md)
6. [テスト戦略](./docs/design/06-test-strategy.md)
7. [技術的リスクと残課題](./docs/design/07-risks-and-open-questions.md)
8. [デプロイ構成](./docs/design/08-deployment.md)

### ADR（docs/adr/）
- 0001: アーキテクチャスタイル（モジュラーモノリス + レイヤードDDD）
- 0002: JV-Link 取り込み方式（Windowsワーカー分離）
- 0003: モノレポ構成
- 0004: PCI / RPCI / PCI3 計算式の隔離方針
- 0005: 想定RPCI 予測戦略（MVPルールベース + ML疎結合IF）
- 0006: DB 3層化（raw / core / mart）
- 0007: フロントエンド構成（Next.js App Router + OpenAPI 型共有）
- 0008: 展開コメント生成方式（ルールベースNLG + LLM疎結合IF）

---

## アーキテクチャ概要

```
[Windows ingestion-worker]
    ↓ (JV-Link/COM → PostgreSQL or Ingest API)
[PostgreSQL (raw / core / mart)]
    ↓
[FastAPI (apps/api)] ──REST──► [Next.js (apps/web)] → Vercel
```

詳細は [`CLAUDE.md`](./CLAUDE.md) および [`docs/`](./docs/) を参照。

---

## MVP スコープ（確定前提）

- 対象: **JRA 中央競馬のみ**、過去5年分
- 更新: **日次バッチ**（前日夜〜当日朝）、リアルタイム速報は対象外
- 公開範囲: **個人利用・検証用途**。生データ非配布、独自指標（PCI/RPCI/PAI/AIコメント）のみ
- 認証・課金: MVP では非対応（将来追加可能な構成）

詳細: [`docs/design/01-requirements.md`](./docs/design/01-requirements.md)
