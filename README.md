# PCI App — 競馬展開予想 SaaS

JRA-VAN DataLab の JV-Link から取得した競馬データを元に、レース展開（ペース・脚質適性）を
自動分析する SaaS アプリ。

> **コアバリュー:** 「PCI を理解していない競馬ファンでも展開予想を活用できること」
>
> TARGET の完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
> **説明可能なアルゴリズム**に変換することが目的。

---

## 現在のステータス

**設計フェーズ完了。** 本リポジトリには現在、設計ドキュメント一式のみが含まれる（実装は未着手）。

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

### ADR（docs/adr/）
- 0001: アーキテクチャスタイル（モジュラーモノリス + レイヤードDDD）
- 0002: JV-Link 取り込み方式（Windowsワーカー分離）
- 0003: モノレポ構成
- 0004: PCI / RPCI / PCI3 計算式の隔離方針
- 0005: 想定RPCI 予測戦略（MVPルールベース + ML疎結合IF）
- 0006: DB 3層化（raw / core / mart）

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
