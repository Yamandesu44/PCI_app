# 設計書 05: 開発ロードマップ

## 1. 基本思想

**Walking Skeleton（1レースをend-to-endで貫通）→ 横展開。**
実データ取り込み（重い）より先に、fixtures/サンプルで価値検証を先行する。

---

## 2. Sprint ロードマップ（2週間/Sprint想定）

| Sprint | ゴール | 主要成果物 |
|---|---|---|
| **S0** 基盤 | 開発できる状態 | モノレポ雛形, CI(mypy strict/Ruff/pytest/import-linter), docker-compose, ADR 0001-0006, CLAUDE.md, fixtures方針 |
| **S1** ドメイン核 | Linux上で完結する中核ロジック | VO群, 脚質判定(C9), PciCalculator（ゴールデン/プロパティテスト）。外部依存ゼロ・最高価値 |
| **S2** データ基盤 | 1レースをDBに載せる | core/mart スキーマ+Alembic, Repository(+testcontainers), サンプルデータ投入経路 |
| **S3** 取り込み | 実データ取得 | ingestion-worker（Windows, JV-Linkパーサ RA/SE/UM/KS/CH）, 内部Ingest API, 5年バックフィル手順 |
| **S4** 予測核 | 想定RPCI→PAI→合致馬 | RuleBasedRpciForecaster(rule-v1), PaceAdaptabilityScorer, 展開シナリオ生成, 根拠生成 |
| **S5** API+UI | 公開可能なMVP | `/forecast`等API, Next.js（一覧→予想ページ＋可視化）, Vercel/コンテナ配備, E2Eスモーク |
| **S6+** Should | 品質・拡張 | PCI/PCI3表示, TARGET差異検証ハーネス, 補正(コース/馬場/騎手/枠), AIコメント |
| **将来** Could | 高度化 | LightGBM RPCI＋SHAP, Pace Confidence, ランキング強化 |

---

## 3. MVP公開までの最短実装順序（クリティカルパス）

```
1. S0 雛形+CI+品質ゲート+ADR(0001-0006)+CLAUDE.md
2. S1 ドメイン核（VO→脚質判定→PciCalculator, ゴールデン/プロパティテスト）  ← 外部依存ゼロ・最高価値
3. S2 DBスキーマ(core/mart)+Alembic+Repository(+testcontainers)+サンプル1レース投入
4. （薄い縦切り）1レースを 脚質→想定RPCI(rule-v1)→PAI→合致馬 まで貫通
5. S4 RpciForecaster/PAI/展開シナリオ/根拠生成（application）
6. S5 /forecast 等API → Next.js（一覧→予想ページ＋可視化）→ 配備(API:コンテナ, DB:マネージド, web:Vercel)
7. S3 ingestion-worker（Windows, JV-Linkパーサ, 5年バックフィル）で実データ供給に切替
8. E2Eスモーク → MVP公開
```

**ポイント:** ③④で1レースをend-to-end貫通（Walking Skeleton）させてから横展開。
実データ取り込み（⑦）は重いので、初期は fixtures/サンプルで価値検証を先行する。

---

## 4. 受入基準（MVP）

| 項目 | 基準 |
|---|---|
| 想定RPCI精度 | MAE ≤ 1.5（vs 実績RPCI） |
| 展開分類精度 | 3分類一致率 ≥ 60% |
| 品質 | mypy --strict 0エラー / Ruff 0エラー / pytest green / 依存方向OK |
| 説明可能性 | 全予測結果に reasons 付与 |
| データ範囲 | JRA中央・過去5年・日次バッチ |
