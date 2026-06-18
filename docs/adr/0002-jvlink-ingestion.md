# ADR-0002: JV-Link 取り込み方式 — Windowsワーカー分離

- **Status:** Accepted
- **Date:** 2026-06-16
- **Deciders:** @yamandesu44

---

## Context

JV-Link（JRA-VAN DataLab データ取得コンポーネント）はWindows専用のCOM/ActiveXコンポーネントであり、
Linux/クラウド環境から直接呼び出すことができない。

一方、FastAPI / PostgreSQL はLinux/クラウドで稼働させたい。

---

## Decision

**Windowsワーカープロセスとして物理分離**する。

### システム構成

```
┌────────────────────────────────┐
│  Windows PC / VM               │
│  apps/ingestion-worker/        │
│    ├── JV-Link COM 呼び出し     │
│    ├── 固定長レコードパーサ      │
│    └── 内部Ingest API 呼び出し  │
└─────────────────┬──────────────┘
                  │ HTTP (内部ネットワーク or VPN)
┌─────────────────▼──────────────┐
│  Linux / Cloud                 │
│  ├── FastAPI (apps/api)        │
│  │     └── POST /internal/ingest  ← 内部エンドポイント
│  └── PostgreSQL                │
└────────────────────────────────┘
```

### 取り込みスコープ（MVP）

- **対象:** JRA 中央競馬のみ（地方競馬はMVP対象外）
- **更新頻度:** 日次バッチ（前日夜〜当日朝）
- **速報系:** MVP 対象外（将来拡張で対応）
- **バックフィル:** 過去5年分

### 対象レコード種別（JV-Link）

| レコード種別 | 内容 | 優先度 |
|---|---|---|
| RA | レース詳細 | MVP必須 |
| SE | 馬毎レース情報（成績） | MVP必須 |
| UM | 馬マスタ | MVP必須 |
| KS | 騎手マスタ | MVP必須 |
| CH | 調教師マスタ | MVP |

### フィクスチャによる開発方針

開発時はJV-Link環境なしで進めるため、
`apps/ingestion-worker/fixtures/` に代表的なサンプルレコードを整備する。

domain / application / API の開発はすべてfixturesで行う。

---

## Consequences

**ポジティブ:**
- FastAPI / PostgreSQL はLinux/クラウドで完結（スケーラブル）
- JV-Link環境なしでdomain・application・APIの開発が可能
- 将来、JV-Link代替（外部データAPI等）への換装時はworkerのみ変更

**ネガティブ:**
- Windowsワーカーの運用・監視が必要（タスクスケジューラ or WindowsサービスでJob管理）
- ネットワーク設定（WorkerからAPIへのアクセス許可）が必要

**緩和策:**
- `apps/ingestion-worker/fixtures/` にサンプルレコードを整備し、JV-Link依存ゼロの開発環境を実現
- Ingest API は認証トークンで保護する（内部エンドポイント）
