# PCI App — 競馬展開予想 SaaS

JRA-VAN DataLab の JV-Link から取得した競馬データを元に、レース展開（ペース・脚質適性）を
自動分析する SaaS アプリ。

> **コアバリュー:** 「PCI を理解していない競馬ファンでも展開予想を活用できること」
>
> TARGET の完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
> **説明可能なアルゴリズム**に変換することが目的。

---

## 現在のステータス

**個人利用MVPは稼働中。少人数ロケテストへ向けて予想検証データを蓄積中。**

| 領域 | 状態 |
|---|---|
| ドメイン核（PCI / 脚質 / 想定RPCI / PAI / 展開シナリオ） | ✅ 実装済み・テスト済み |
| アプリケーション層（ユースケース） | ✅ 実装済み |
| DB（core / mart）+ Alembic + Repository | ✅ 実装済み（mart 永続化込み） |
| FastAPI（`/forecast`・レース詳細） | ✅ 実装済み |
| 型共有（`packages/api-client`） | ✅ OpenAPI → TypeScript 生成 |
| フロントエンド（`apps/web` / Next.js） | ✅ レース一覧・展開予想・確定後分析・予想検証 |
| ingestion-worker（mykeibadb / JV-Link） | ✅ Windows自動同期・鮮度/完全性監視・失敗通知 |
| 実データ | ✅ mykeibadb（MySQL）からPostgreSQLへ同期 |
| 予想精度の期間外検証 | ⏳ 2026-07-25以降の事前予想を蓄積中 |
| 少人数ロケテスト | ✅ Quick Tunnel実URLで認証・API疎通・代表3レースを確認済み。招待開始時だけ公開する |

ローカル起動: API は [`apps/api/README.md`](./apps/api/README.md)、Web は [`apps/web/README.md`](./apps/web/README.md) を参照。

---

## ドキュメント

| 種別 | 場所 |
|---|---|
| プロジェクト指針（必読） | [`CLAUDE.md`](./CLAUDE.md) |
| 現在の引き継ぎ | [`docs/HANDOFF.md`](./docs/HANDOFF.md) |
| 現行仕様 | [`docs/SPEC.md`](./docs/SPEC.md) |
| ロケテスト手順 | [`docs/LOCATION_TEST.md`](./docs/LOCATION_TEST.md) |
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

## 現行スコープ

- 対象: **JRA 中央競馬のみ**、過去5年分
- 更新: **日次バッチ**（前日夜〜当日朝）、リアルタイム速報は対象外
- 公開範囲: 現在は**個人利用・検証用途**。次段階は招待した少人数だけのロケテスト
- データ表示: 生データやPCI/RPCI等の内部実数値を前面に出さず、独自の言葉・段階評価へ翻訳
- 認証・課金: 少人数テスト用の共有認証のみ実装。個別アカウント・権限・課金は対象外

詳細: [`docs/design/01-requirements.md`](./docs/design/01-requirements.md)

## デプロイ

### API（Railway / Render / Fly.io など）

`apps/api/Dockerfile` はどのPaaSでも動くよう、固有の仕組みを使わない。ポートは
`PORT` 環境変数で受ける（未設定なら 8000）。

```bash
docker build -t pci-api apps/api
docker run -p 8000:8000 -e DATABASE_URL=... -e PUBLIC_API_TOKEN=... pci-api
```

**マイグレーションはイメージ側で自動実行しない。** 複数インスタンスが同時起動すると
競合するため、デプロイ手順で1回だけ流すこと。

```bash
alembic upgrade head
```

必ず設定する環境変数:

| 変数 | 未設定だとどうなるか |
|---|---|
| `DATABASE_URL` | ローカル既定を見に行き接続できない |
| `PUBLIC_API_TOKEN` | **`/api/v1/*` が無認証で全公開**（起動時に警告が出る） |
| `INGEST_TOKEN` | `/internal/ingest/*` が無認証 |
| `CORS_ALLOW_ORIGINS` | ローカル開発の2オリジンのみ許可（公開フロントからは弾かれる） |
| `RATE_LIMIT_TRUSTED_PROXIES` | **全利用者が同じキーへ集約され、実質「全体で120回/分」になる** |

レート制限は既定で 120回/分・クライアント単位（`RATE_LIMIT_PER_MINUTE=0` で無効）。
ロードバランサ配下では `RATE_LIMIT_TRUSTED_PROXIES` に段数を設定しないと、
接続元IPが常にプロキシになるため制限が全利用者で共有されてしまう。

CI はイメージのビルドと `/health` 応答までを毎回検証する（`docker` ジョブ）。
レジストリへの push は入れていない。デプロイ先が決まってから足すこと。

### web（Vercel）

ルートの `vercel.json` が設定を持つ。`API_BASE_URL` を Vercel の環境変数へ入れる。
公開する場合は API 側の `PUBLIC_API_TOKEN` と web 側の `API_ACCESS_TOKEN` を揃える。

### 手元で本番と同じイメージを動かす

```bash
docker compose --profile api up --build api
```
