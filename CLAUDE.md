# PCI App — 競馬展開予想 SaaS

## プロジェクト概要

JRA-VAN DataLabのJV-Linkから取得した競馬データを元に、レース展開（ペース・脚質適性）を
自動分析するSaaSアプリ。

**コアバリュー:** 「PCIを理解していない競馬ファンでも展開予想を活用できること」

TARGETの完全再現ではなく、上級者の暗黙知（展開判断・展開合致馬抽出）を
説明可能なアルゴリズムに変換することが目的。

---

## アーキテクチャ地図

```
[Windows ingestion-worker]
    ↓ (JV-Link/COM → PostgreSQL or Ingest API)
[PostgreSQL (raw / core / mart)]
    ↓
[FastAPI (apps/api)] ──REST──► [Next.js (apps/web)] → Vercel
```

**スタイル:** モジュラーモノリス + レイヤードDDD

**依存方向（厳守・CIのimport-linterで強制）:**

```
domain          ← 外部依存ゼロ（標準ライブラリのみ）
   ↑
application     ← domain のみ参照
   ↑
infrastructure  ← application, domain を参照
presentation    ← application, domain を参照
```

逆流は一切禁止。domain 層から SQLAlchemy・Pydantic・FastAPI を import しない。

---

## ディレクトリ概要

```
pci_app/
├── apps/
│   ├── api/
│   │   ├── src/pci/
│   │   │   ├── domain/
│   │   │   │   ├── shared/        # VO: RaceKey, Distance, RaceTime, ...
│   │   │   │   ├── racing/        # Race, RaceEntry, Horse エンティティ
│   │   │   │   └── pace/          # ★PCI・RPCI・脚質・PAI（式を隔離）
│   │   │   │       ├── pci.py           # PCI計算（唯一の真実の場所）
│   │   │   │       ├── running_style.py # 脚質判定
│   │   │   │       ├── rpci_forecast.py # 想定RPCI予測（戦略IF）
│   │   │   │       ├── adaptability.py  # PAI・展開合致
│   │   │   │       └── commentary.py    # 展開コメント生成（戦略IF・comment-v1）
│   │   │   ├── application/       # ユースケース（アプリサービス）
│   │   │   ├── infrastructure/    # SQLAlchemy, Repository 実装, DI
│   │   │   ├── presentation/      # FastAPI routers, Pydantic schemas
│   │   │   └── config/
│   │   ├── tests/
│   │   │   ├── unit/              # ドメイン純粋単体テスト
│   │   │   ├── integration/       # testcontainers-postgres
│   │   │   └── contract/          # API スキーマ契約テスト
│   │   ├── alembic/
│   │   └── pyproject.toml
│   ├── web/
│   │   └── src/{app,features,components,lib}/
│   └── ingestion-worker/
│       ├── src/                   # JV-Link COM 呼び出し + 固定長パーサ
│       └── fixtures/              # サンプル JV-Data レコード（開発用）
├── packages/
│   └── api-client/                # OpenAPI 生成 TS 型・クライアント
├── docs/
│   ├── adr/                       # Architecture Decision Records
│   ├── domain/                    # ユビキタス言語
│   └── design/                    # 設計書
├── CLAUDE.md
├── docker-compose.yml
└── README.md
```

---

## ユビキタス言語（必ず統一して使うこと）

| 用語 | 定義 |
|---|---|
| **PCI** (Pace Change Index) | 個馬の1走における前半/後半ペース比率指数。>50=スロー、<50=ハイ、=50=イーブン |
| **RPCI** (Race PCI) | レース全体のペース指数。実績値（確定後）と想定値（予測）がある |
| **PCI3** | 上位3着馬の PCI 平均。レース代表ペース指標 |
| **脚質** | 過去5走の4角通過順位から算出。逃/先/差/追/自在 の5分類 |
| **PAI** (Pace Adaptability Index) | 想定 RPCI への馬の適性指数。0〜100、高いほど展開合致 |
| **想定 RPCI** | 出走馬の脚質構成・距離・コース・馬場から予測した RPCI。本プロダクトの中核 |
| **展開合致馬** | PAI が高く、想定ペースで恩恵を受けると判定された馬 |
| **展開コメント** | 指標（想定RPCI・PAI・PCI）を非専門家向けの自然文へ翻訳した解説。出走前=予想／確定後=回顧。AIコメントの実体 |
| **上がり3F** | ゴール前3ハロン(600m)の走破タイム（秒） |
| **通過順位** | 各コーナー通過時点での順位（1〜4角） |
| **RaceKey** | レース識別子 16桁: 年(4)+月日(4)+競馬場コード(2)+回(2)+日目(2)+R(2) |
| **raw層** | JV-Link からの原文データ。追記のみ・改変禁止 |
| **core層** | 正規化済みドメインデータ（races, race_entries 等） |
| **mart層** | 分析結果（predicted_pace, pace_fit 等）。model_version 付き・再計算可能 |
| **formula_version** | PCI 計算式のバージョン（例: "pci-v1"） |
| **model_version** | 予測モデル／生成器のバージョン（例: "rule-v1", "pai-v1", "comment-v1", "lgbm-v2"） |

詳細定義: `docs/domain/ubiquitous-language.md`

---

## PCI 式の管理（最重要ルール）

**唯一の真実の場所:** `apps/api/src/pci/domain/pace/pci.py`

- PCI / RPCI / PCI3 の計算はここ**だけ**に書く
- 他の場所から直接式を書かない（呼び出しのみ可）
- `formula_version` を全算出結果に付記する
- 式変更時は**ゴールデンテストを必ず更新**し、変更根拠をコミットメッセージに記載

---

## コーディング規約

- 型ヒント 100%、`mypy --strict` 0 エラー
- Ruff（linter + formatter）
- domain 層は純粋 Python・標準ライブラリのみ（SQLAlchemy/Pydantic/FastAPI 禁止）
- VO（値オブジェクト）は不変（frozen dataclass または NamedTuple）・コンストラクタで自己検証
- すべての算出結果に `reasons: list[Reason]` を付ける（説明可能性の原則）
- コメントは「WHY（なぜそうするか）」が非自明な場合のみ記載

---

## テスト規約

| 層 | 手段 | 目標カバレッジ |
|---|---|---|
| domain (pace 核) | pytest 純粋単体 + **ゴールデンテスト** + プロパティテスト(hypothesis) | 95%+ |
| application | Fake Repository 使用の単体テスト | 80%+ |
| infrastructure | testcontainers-postgres 統合テスト | 主要パス |
| presentation | FastAPI TestClient + スキーマスナップショット | 主要エンドポイント |

ゴールデンテストの場所: `apps/api/tests/unit/domain/pace/test_pci_golden.py`

プロパティテストの不変条件例:
- 均等ペース（前後同じタイム/F）→ PCI ≈ 50
- 上がりが速いほど PCI 高（スロー方向）
- 距離が変わっても均等ペース条件では PCI ≈ 50

---

## 頻用コマンド

```bash
# テスト（全体）
cd apps/api && pytest tests/

# テスト（ドメイン層のみ・高速）
cd apps/api && pytest tests/unit/domain/

# 型チェック
cd apps/api && mypy src/ --strict

# Lint
cd apps/api && ruff check src/ tests/

# ローカル DB 起動
docker-compose up -d db

# マイグレーション適用
cd apps/api && alembic upgrade head

# OpenAPI → TS 型生成
cd packages/api-client && npm run generate

# 予測精度バックテスト（想定RPCI 誤差 + PAI リフト）
cd apps/api && python -m scripts.backtest_forecast --limit 200
```

---

## JV-Link / 取り込み注意事項

- JV-Link は Windows 専用（COM/ActiveX）。`apps/ingestion-worker/` は Windows 環境専用
- **開発時は `apps/ingestion-worker/fixtures/` のサンプルレコードを使う**
  - domain / application / API の開発は JV-Link 環境なしで可能
- JV-Link 認証情報（SID 等）を**絶対にコミットしない**（`.env` で管理）
- 取り込みスコープ: JRA 中央競馬のみ、日次バッチ（前日夜〜当日朝）

---

## 法務・セキュリティ

- JRA-VAN データの**生データ再配布は禁止前提**
- 公開するのは独自指標・分析結果（PAI、展開予想、AIコメント等）のみ
- MVP は個人利用・検証用途。正式公開時は規約確認が必要
- 機密情報（API キー、DB 接続文字列等）は `.env` で管理し、`.gitignore` に記載

---

## ADR の場所と起票基準

場所: `docs/adr/NNNN-title.md`（MADR 形式）

**起票すべきもの:** アーキ決定・技術選定・データ契約・式/モデル方針など「後で覆すと高コスト」な決定

現状の ADR:
- 0001: アーキテクチャスタイル（モジュラーモノリス + レイヤードDDD）
- 0002: JV-Link 取り込み方式（Windowsワーカー分離）
- 0003: モノレポ構成
- 0004: PCI 式の隔離方針
- 0005: RPCI 予測戦略（MVPルールベース + ML疎結合IF）
- 0006: DB 3層化（raw/core/mart）
- 0007: フロントエンド構成（Next.js App Router + OpenAPI 型共有）
- 0008: 展開コメント生成方式（ルールベースNLG + LLM疎結合IF）
- 0009: ペース指標カラムの配置（core 層 confirmed PCI 埋め込み + mart 層版管理分離）

---

## Definition of Done

- [ ] 型ヒント 100% / `mypy --strict` 0 エラー
- [ ] Ruff 0 エラー
- [ ] pytest green（新機能にはテスト追加）
- [ ] domain 層に外部依存なし（import-linter で確認）
- [ ] 算出結果に `reasons` 付き（説明可能性）
- [ ] mart 層の結果に `model_version` または `formula_version` を記録
- [ ] 生データ・認証情報がコミットに含まれていない
