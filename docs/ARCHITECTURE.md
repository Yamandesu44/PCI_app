# ARCHITECTURE — システム構成（現状のコード調査に基づく）

> 本ファイルは現在のコードを調査して整理したもの。**推測を含む箇所には「（推測）」を明記**する。
> 確定した設計判断の背景は `docs/adr/` を参照。

最終調査: 2026-07-12 / 対象コミット `2b083ba` / ブランチ `claude/sweet-einstein-ilnaov`

---

## 1. システム全体構成

```
[apps/ingestion-worker]  (Windows 実行機)
    JV-Link COM  または  mykeibadb(MySQL)  → 固定長パーサ
        │  HTTP (POST /internal/ingest/*  X-Ingest-Token)
        ▼
[apps/api]  FastAPI（モジュラーモノリス + レイヤードDDD）
    presentation → infrastructure → application → domain
        │  SQLAlchemy
        ▼
[PostgreSQL]  3層: raw / core / mart
        ▲
        │  REST (/api/v1/*)  + OpenAPI
[packages/api-client]  OpenAPI → TypeScript 型・クライアント
        ▲
        │  import
[apps/web]  Next.js 15 App Router → Vercel（配備設定 vercel.json）
```

モノレポは npm workspaces（`packages/*`, `apps/web`）。Python 側（api / ingestion-worker）は
それぞれ独立した pyproject を持つ。

---

## 2. 各ディレクトリの役割

### apps/api（FastAPI バックエンド, Python 3.11+）
```
src/pci/
  domain/            外部依存ゼロ（標準ライブラリのみ）
    shared/          VO: RaceKey, Distance, RaceTime, Furlong3Time, CornerPositions, Reason
    racing/          エンティティ: Race, RaceEntry, Horse/Jockey/Trainer マスタ, Repository Protocol
    pace/            ★計算核（式を隔離）
      pci.py         PCI / RPCI / PCI3 計算（唯一の真実の場所・formula_version）
      running_style.py 脚質判定（4角順位の確定判定 + 対象距離対応の混在型予測）
      rpci_forecast.py 想定RPCI 予測（戦略IF + rule-v4 実装 + classify_pace + 答え合わせ）
      adaptability.py  PAI・展開合致（pai-v1）
      affinity.py      過去好走から得意ペースを推定
      formation.py     枠順確定判定 + 4ゾーンの序盤隊列予想（formation-v1）
      commentary.py    展開コメント生成（戦略IF + comment-v1 ルールベースNLG）
      scenario.py      展開シナリオ見出し/詳細
      mart_repository.py mart 層 Repository Protocol（read/write）
  application/       ユースケース（forecast / race_query / race / ingest / backtest）+ DTO
  infrastructure/    SQLAlchemy models・database・repositories（race / mart）・pace（lgbm forecaster）
  presentation/      FastAPI app・routers（races / ingest / health）・Pydantic schemas・DI(dependencies)
  config/            設定（settings）
tests/               unit / contract（+ integration は testcontainers）
alembic/             マイグレーション（001 initial, 002 ingest_log）
scripts/             export_openapi.py, backtest_forecast.py
```

### apps/web（Next.js 15 / React 19 / Tailwind）
```
src/
  app/               App Router。page.tsx（レース一覧）、races/[raceKey]/forecast, /pace-analysis
  components/        RaceForecastDashboard, RaceHero, PaceHeadline, HorseFitTable,
                     PaceAnalysisTable, PaceProfileChart, CommentCard, ReasonList,
                     RaceDateCalendar, FormationView, ui/（accordion/card/progress）
  lib/               api.ts（API 呼び出し）, pace.ts（★ペース表現の翻訳層）,
                     races.ts（一覧の分類整形）, raceSchedule.ts, utils.ts
                     *.test.ts（vitest）
```

### apps/ingestion-worker（取り込みバッチ, Python 3.12+ / Windows 前提）
```
src/ingestion/
  batch.py           エントリポイント（--mode fixture|jvlink|mykeibadb, --step, --date/--date-to）
  ingest_api.py      Ingest API HTTP クライアント（log_batch 含む）
  client/            base(Protocol) / fixture / windows(JV-Link COM) / mykeibadb(MySQL)
  parser/            ra_parser, se_parser, master_parsers, jv_spec（★バイトオフセットの真実の場所）, common
  models.py          中間データモデル
scripts/             run_mykeibadb_full_sync.ps1, run_batch.ps1, sync_mykeibadb.bat,
                     setup_task_scheduler.ps1（Task Scheduler 自動化）
fixtures/            開発用サンプル JV-Data（Windows/JV-Link 不要で開発可能）
```

### packages/api-client
OpenAPI（`openapi.json`）から TypeScript 型を生成。web が唯一の API 型ソースとして参照。

---

## 3. データの流れ

### 取り込み（確定前・確定後）
1. `mykeibadb.exe`（別ツール）が JV-Link → ローカル MySQL を最新化（現運用の主経路）。
2. `batch.py --mode mykeibadb --step entries/results` が MySQL を読み、固定長レコードへ整形。
3. `IngestApiClient` が `POST /internal/ingest/{horses,jockeys,trainers,entries,results}` へ送信。
4. API 側ユースケース（`RegisterRaceEntriesUseCase` / `RecordRaceResultUseCase`）が
   PCI 算出・RPCI/PCI3 集計・脚質判定を行い core 層へ保存。実行ログは `ingest_log` に記録。

### 予測（出走前）
- `GET /api/v1/races/{key}/forecast` → `ForecastRaceUseCase` が想定RPCI（rule-v4）・PAI・展開コメントを算出。
- 全馬の実枠番が1〜8なら、脚質・近走序盤位置から `formation-v1` の4ゾーン隊列も算出。
  従来判定で脚質が混在する馬だけ、対象距離と過去走距離を加味した `running-style-v2-distance` で
  今回向けの脚質へ具体化する。履歴なしは自在のまま「参考」とする。
  特別登録（`frame_no=0`）では `formation=null` とし、Webも非表示にする。
- 結果は mart 層 `predicted_pace` / `pace_fit` に `model_version` 付きで**永続化**（upsert）。

### 回顧（確定後）と答え合わせ
- `GET /api/v1/races/{key}/pace-analysis` → `GetPaceAnalysisUseCase` が確定 PCI/RPCI/PCI3 を再集計し、
  mart 層に保存済みの想定RPCI を引き当てて `forecast_accuracy`（的中/外れ）を返す（本セッションで追加）。

### 表示
- web が API から DTO を取得し、`lib/pace.ts` 等で実数値を言葉・バー・色に翻訳して表示。

---

## 4. 外部サービスとの連携

| 連携先 | 用途 | 備考 |
|---|---|---|
| JV-Link（JRA-VAN DataLab） | 原データ取得 | Windows 専用 COM。現状は mykeibadb 経由が主（ADR-0002） |
| mykeibadb（MySQL） | JV-Data のローカル蓄積 | `wmykeibadb.exe` で投入。列名は環境で揺れる（候補列で吸収） |
| PostgreSQL | 本体 DB（raw/core/mart） | docker-compose で起動 |
| Vercel | web デプロイ | vercel.json |
| Slack 互換 Webhook | バッチ失敗通知（任意） | `NOTIFY_WEBHOOK_URL` |
| Gemini（LLM） | 展開コメント（任意・疎結合） | `GEMINI_API_KEY` 設定時のみ。未設定はルールベース（推測: 現状ほぼルールベース運用） |

---

## 5. DB・API・画面の関係

| 画面 | API | 主なテーブル |
|---|---|---|
| レース一覧（`app/page.tsx`） | `GET /api/v1/races`, `/races/dates` | core: races |
| 展開予想（`races/[key]/forecast`） | `GET /api/v1/races/{key}/forecast` | core: races/race_entries, mart: predicted_pace/pace_fit（書込） |
| ペース分析/回顧（`races/[key]/pace-analysis`） | `GET /api/v1/races/{key}/pace-analysis` | core: races/race_entries, mart: predicted_pace（読込・答え合わせ） |
| （内部）取り込み | `POST /internal/ingest/*` | core 全般 + ingest_log |

---

## 6. 主要ドメインモデル

- **RaceKey**（VO）: 16桁識別子（年4+月日4+競馬場2+回2+日目2+R2）。
- **Race**（エンティティ）: status（entries/result）で確定前後を同一集約で管理。確定後は rpci_actual/pci3_actual を持つ。
- **RaceEntry**: 出走馬。確定後に finish_pos/race_time/agari_3f/corner_1..4/pci_actual/running_style が埋まる。
- **PciResult / RpciResult**: pci.py の算出結果（value/formula_version/reasons）。
- **RpciForecast**: 想定RPCI（value/label/confidence/model_version/reasons）。
- **PaiResult**: 展開適性（pai/fit_label/model_version/reasons）。
- **HorsePaceAffinityProfile**: 過去好走から得た得意ペース分布（隣接レベルへのにじみ込み）。
- **Commentary**: 自然文の展開コメント（headline/body/model_version/reasons）。
- **ForecastAccuracy**: 想定 vs 実績の答え合わせ（error/label_hit）。
- **FormationPrediction**: 枠順確定後の序盤隊列（先頭/好位/中団/後方、model_version/reasons付き）。

---

## 7. 現時点で分かる技術的制約

- JV-Link は Windows 専用 COM、かつ**32bit 版**でしか COM 登録されていない環境がある
  （64bit Python からは `クラスが登録されていません`）。現運用は mykeibadb 経由で回避。
- mykeibadb のテーブル名・列名は環境/バージョンで揺れる（候補名リストで吸収）。
- `mypy src/ --strict` は infrastructure/presentation で SQLAlchemy/Pydantic/FastAPI の
  スタブ未導入により多数エラーになる（**環境要因・コード欠陥ではない**）。domain/application は clean。
- Windows PowerShell 5.1 は BOM 無し UTF-8 を ANSI(CP932) で誤読するため、
  自動実行スクリプトは**純 ASCII**で書く（日本語コメント混入で過去にクラッシュ）。
- 開発は `fixtures/` で JV-Link/Windows なしに domain/application/API を進められる。
