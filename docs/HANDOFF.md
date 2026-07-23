# HANDOFF — 現在の作業状態

## 2026-07-23 19:42 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `d946adb`
- 実装最新コミット: `6fda136`
- 今回の目的: 馬場情報バックフィル後の実DBで小倉芝1200mを馬場状態別に再検証し、参考表示の妥当性を確定する。

### 完了した内容

1. `apps/api/src/pci/application/backtest.py`
   - 脚質別有利度の内訳へ`distance-track-condition`を追加した。
   - `1200m / 良`のようなラベルと、距離・馬場状態順の安定した並びを実装した。
2. `apps/api/scripts/backtest_forecast.py`
   - `--style-breakdown distance-track-condition`を選択可能にした。
3. `apps/api/src/pci/domain/pace/style_advantage.py`
   - 7月小倉芝1200mの参考理由へ「馬場状態別でも同じ傾向」を追記した。
   - 参考条件、スコア、PAI、順位、仮係数は変更していない。
4. 実DB再検証
   - 対象: 2025-07-01〜2026-07-31、小倉芝199レース・1534頭。
   - 1200m: 良-22.4pt（45R）、稍重-10.5pt（12R）、重-9.0pt（6R）、不明-26.4pt（27R）。
   - 確認できた全馬場状態で逆転方向が続いたため、`style-advantage-v3`の参考条件を維持した。
   - 1800m・2000mは馬場状態ごとに正負が混在し、参考範囲を拡張する根拠はなかった。

### 未完了・既知の問題

- 今回のタスクに未完了実装はない。
- 「不明」27レースは主に直近365日の補完開始より前の2025年データを含む。今回の既知馬場3区分が
  すべて同方向のため判断は可能だが、監視窓より前まで再補完する場合は同じコマンドで再診断する。
- `StyleAdvantageWeights`は引き続き仮係数。今回の結果だけで反転・補正しない。
- API非統合テスト全体の既知状態は509 passed / 3 failed。失敗は既存のcaplogログ捕捉テストで、
  今回の対象テスト49件は成功した。
- 実運用cloneの既存未追跡`apps/ingestion-worker/.env]`と`result_run.txt`には触れていない。

### テスト結果

- API対象:
  `python -m pytest tests/unit/application/test_backtest.py tests/unit/domain/pace/test_style_advantage.py -q`
  -> 49 passed
- API Ruff: `python -m ruff check src tests scripts/backtest_forecast.py` -> passed
- API mypy: `python -m mypy src --strict --python-version 3.12` -> passed（63 source files）
- import-linter: `lint-imports.exe` -> 2 contracts kept / 0 broken
- 実DB診断:
  `python -m scripts.backtest_forecast --validate-style-advantage --track-type 芝 --venue-code 10
  --date-from 2025-07-01 --date-to 2026-07-31 --style-breakdown distance-track-condition`
  -> 199レース・1534頭を集計、正常終了

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`
3. `docs/SPEC.md`
4. `docs/DECISIONS.md`
5. `apps/api/src/pci/application/backtest.py`
6. `apps/api/src/pci/domain/pace/style_advantage.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_backtest.py tests/unit/domain/pace/test_style_advantage.py -q
python -m scripts.backtest_forecast --validate-style-advantage --track-type 芝 --venue-code 10 `
  --date-from 2025-07-01 --date-to 2026-07-31 --style-breakdown distance-track-condition
```

## 2026-07-23 19:31 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `48ddac3`
- 実装最新コミット: `dfcb0d7`
- 今回の目的: 予想検証サマリーの左右見切れを解消し、ほとんどのレースで欠けていた馬場情報を実データから補完する。

### 完了した内容

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`
   - セクションへ `px-4 sm:px-6` を追加し、見出し・期間切替・指標の左右余白を確保した。
2. `apps/ingestion-worker/src/ingestion/batch.py`
   - `includes_race_metadata()` を追加し、mykeibadb の `--step all` でも補足情報を取り込むようにした。
3. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
   - entries後にrace-metadataを自動実行し、終了コードも全体成否へ含めた。
4. `apps/api/src/pci/application/race_use_cases.py`
   - コース種別・馬場状態・天候を更新する。
   - 正規キーと旧キーが併存する場合、日付・競馬場・R番号が一致する重複レースも同時更新する。
   - 正規キーがない場合は候補が一意のときだけ旧キーを更新し、曖昧な候補は更新しない。
5. `apps/ingestion-worker/src/ingestion/parser/common.py`
   - mykeibadb `track_code` マスタに基づき、TrackCDを芝10〜22、ダート23〜29、障害51〜59へ修正した。
6. 実データ補完
   - 2025-07-23〜2026-07-23を3回検証しながら再補完した。最終全期間実行ログはingest log id=55、12月6日再補完はid=56。
   - 未反映件数は564件から0件。
   - `2026020108010111` は芝・良・曇、`2026071902011211` は芝・重・晴を確認。
   - mykeibadbに存在しない開発用シード `2026061805010101` は内部削除APIで削除した。

### 未完了・既知の問題

- 旧形式キーと正規キーの重複レース自体は残っている。今回は削除・成績統合をせず、馬場情報だけを一致させた。重複整理は別タスクとして、RaceEntry・予想マート等のFK移行設計を先に行うこと。
- API非統合テスト全体は509 passed / 3 failed。失敗は既存のcaplogログ文言取得テスト3件で、今回の対象テスト63件は成功。
- ingestion-worker全体lintは既存14件で失敗する。対象は未変更の `windows_client.py`、`locate_corners.py`、`test_locate_corners.py`。今回変更ファイルのlintは成功。
- 作業用workspaceからユーザーの `.venv` を直接起動するとプロセス生成に失敗したため、テストはシステムPython 3.12で実行した。実運用cloneの `run_batch.ps1` は成功している。
- `C:\Users\yuuta\PCI_app\apps\ingestion-worker\.env]` と `result_run.txt` は既存未追跡ファイルのため触れていない。

### テスト結果

- ingestion-worker: `python -m pytest -q` -> 220 passed
- ingestion-worker変更ファイル: Ruff -> passed
- API対象: `pytest tests/unit/application/test_race_use_cases.py tests/contract/test_ingest_api.py -q` -> 63 passed
- API: Ruff -> passed
- API: mypy strict Python 3.12 -> passed (63 source files)
- Web: Vitest -> 74 passed
- api-client / Web: typecheck -> passed
- Web: `next build` -> passed
- API非統合全体: 509 passed / 3 failed（既存ログ捕捉テスト）

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`
3. `docs/DECISIONS.md`
4. `apps/api/src/pci/application/race_use_cases.py`
5. `apps/ingestion-worker/src/ingestion/parser/common.py`
6. `apps/ingestion-worker/src/ingestion/batch.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
Invoke-RestMethod http://localhost:8000/api/v1/ingest-status
cd apps\ingestion-worker
python -m pytest -q
cd ..\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_race_use_cases.py tests/contract/test_ingest_api.py -q
```

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-23（更新40回目・Codex が予想検証の前期間比較を実装） |
| 作業担当AI | OpenAI Codex |
| 引き継ぎ先 | Claude Code |
| 直前の担当AI | OpenAI Codex（予想検証を直前の同期間と比較可能にした） |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | `HEAD`（本セッションのコミット。作業開始時は `ed04a84`） |
| 作業ツリー | 本セッションのコミット・push後にクリーン化する前提 |

---

## 現在の作業目的

**選択した展開予想の検証期間を、その直前にある同じ日数と比較し、
全体・芝・ダートの変化を判断できるようにした。**

`GetForecastPerformanceUseCase`は現在期間の直前にある同じ日数を前期間として追加取得する。
期間同士は重複せず、30日なら直近30日対その直前30日、180日なら直近180日対その直前180日となる。
`previous_period`は前期間の日付範囲と全体・芝・ダートの一致率・的中数・母数を必須で返す。
比較元0件の場合も期間と3グループを返し、各一致率だけをnullとする。PCI/RPCI実数値は公開しない。

`ForecastPerformanceSummary`は各指標の下へ前期比をパーセントポイントで表示する。
正は上向きアイコンと緑、負は下向きアイコンと黄、差なしは横線と灰色を使い、符号も併記する。
前期間0件は「前期比較なし」とし、恣意的な改善・悪化の閾値は導入していない。

`GET /api/v1/forecast-performance`は`days=30|90|180`を受け付け、未指定時は90日を使う。
一致率、芝・ダート、信頼度別集計、混同行列、検証カバー率は選択期間で再集計する。
`weekly_trend`だけは期間に連動させず、比較軸を揃えるため常に直近8完了週を返す。
application層は30日選択時も8週分を取得し、期間集計用レコードと週次用レコードを分離する。

Webトップの`ForecastPerformanceSummary`へ30日・90日・180日のセグメントを追加した。
`performance_days`と`date`をURLへ保持し、期間と開催日のどちらを先に変更しても他方の選択を失わない。
不正な`performance_days`はWebで90日に戻し、APIの不正な`days`は422となる。

`MartRepository.find_prediction_evaluations()`は、JST基準の指定期間にある確定済みJRA平地から、
レース日以前に生成された最新の予想を1件だけ選ぶ。application層で確定RPCIを展開区分へ変換し、
全体・芝・ダートの一致率、的中数、母数を集計する。公開
`GET /api/v1/forecast-performance`と`ForecastPerformanceSummary`は期間と集計結果だけを扱い、
PCI/RPCIの内部実数値をAPI・画面へ露出しない。`weekly_trend`は進行中の週を除き、
直近8完了週を月曜から日曜の固定区間で返す。WebはRechartsの棒グラフと最新週の母数を表示し、
完了週のデータがない場合は空グラフを出さない。

`confidence_groups`は既存の`confidenceInsight()`と同じ境界を使い、70%以上を「読みやすい」、
50%以上70%未満を「標準」、50%未満を「変動注意」として一致率・的中数・母数を返す。
`ForecastConfidenceCalibration`は3本の横棒と母数を表示する。信頼度別集計は複数モデル世代を
横断するため、個別モデルの校正指標ではなく現在の画面表示全体の実績として解釈すること。

`pace_matrix`は「速い・平均・落ち着く」の予想3区分を行、実績3区分を列として、
各セルの件数と行内割合を返す。`ForecastErrorPattern`はトップ画面の情報密度を抑えるため
native `details`で既定は閉じ、一致セルを緑、不一致セルを黄で表示する。モバイルは
最小幅430pxの表を横スクロールし、文字や数値を縮めすぎない。

`MartRepository.count_prediction_evaluation_candidates()`は、指定期間の確定済みJRA平地かつ
`rpci_actual`を持つレースを、予想martの有無と独立に集計する。APIは`eligible_race_count`と
`coverage_rate = sample_size / eligible_race_count`を返し、対象0件ならnullとする。
`ForecastEvaluationCoverage`は照合済み件数／対象総数を進捗バーで表示し、全件なら緑、
未保存が残る場合は黄とする。任意の品質閾値は導入していない。

`ForecastPerformanceTrend`は約100KBのRecharts依存を持つため、
`ForecastPerformanceTrendLazy`から`next/dynamic`で遅延読み込みする。直接importした試作では
一覧のFirst Load JSが214KBまで増えたが、遅延化後は110KBへ戻った。

今回の検証は対象単体・契約11 passed、OpenAPIスナップショット2 passed、Web 74 passed。
API Ruff、API全体63ファイルのmypy strict、OpenAPI生成、api-client/Web typecheck、
Web production buildは成功し、一覧のFirst Load JSは110KBを維持した。今回はRepositoryを
変更していないためPostgreSQL統合テストとAPI非統合全体は再実行していない。Web workspaceには
lintスクリプトがないため実行不可（Next buildもlintをskipする）。グローバルPythonには
`lint_imports`が未導入のためimport境界チェックも実行不可だが、application/domainの依存方向は
既存構成に従っている。

既知の制約として、レース発走・結果確定時刻をDBに保持していないため、レース当日に終了後生成された
予想は日付比較だけでは除外できない。通常の`--step forecasts`による事前生成を前提とし、時刻列を
導入した場合に厳密化する。コード実装は完了しており、作業が止まっている箇所はない。

Claude Codeが最初に確認するファイル:
`apps/api/src/pci/application/forecast_performance_use_cases.py`,
`apps/api/src/pci/presentation/routers/status.py`,
`apps/api/src/pci/infrastructure/repositories/mart_repository.py`,
`apps/web/src/components/ForecastConfidenceCalibration.tsx`,
`apps/web/src/components/ForecastEvaluationCoverage.tsx`,
`apps/web/src/components/ForecastErrorPattern.tsx`,
`apps/web/src/components/ForecastPerformanceTrend.tsx`,
`apps/web/src/components/ForecastPerformanceTrendLazy.tsx`,
`apps/web/src/components/ForecastPerformanceSummary.tsx`,
`apps/web/src/components/RaceDateCalendar.tsx`,
`docs/DECISIONS.md`。
最初に実行するコマンド:
`git status --short --branch`、
`cd apps/api && set PYTHONPATH=src && python -m pytest tests/unit/application/test_forecast_performance_use_cases.py tests/contract/test_status_api.py -q`、
`npm.cmd run typecheck --workspace=@pci/web`。

### 前タスク（馬場状態欠損監視）

`GET /api/v1/ingest-status`は、従来のバッチ鮮度・成績未取込に加えて、JST基準の直近365日、
開催日前日まで、`status=result`、JRA10場、平地、`track_condition IS NULL`の件数と
新しい順の代表20件を返す。地方・障害・出走前・365日より古いレースは警告対象外。
Webトップの`IngestStatusBanner`は「馬場情報未反映」として別表示し、対象レースの回顧画面と
専用`race-metadata`コマンドへ案内する。`run_batch.ps1`へ`-ChunkDays`を追加したため、
1年分を7日単位で処理できる。

関連API単体・契約15 passed、PostgreSQL統合1 passed、Web 74 passed。
API全体Ruff、mypy strict（62ファイル）、OpenAPI同期、api-client/Web typecheck、Web buildは成功。
API非統合全体は500 passed / 3 failed / 23 deselected。失敗3件は従来からの`caplog`順序依存で、
単独再実行は3 passed。今回変更したテストに失敗はない。

実mykeibadb/PostgreSQLへのバックフィルはこの環境から接続できないため未実行。
Windows実行機でWeb警告に表示されるコマンド、または下記をリポジトリ直下から実行し、
警告が消えることを確認してから馬場状態別の小倉芝1200m診断を再実行する。

```cmd
powershell -ExecutionPolicy Bypass -File apps\ingestion-worker\scripts\run_batch.ps1 -Step race-metadata -Mode mykeibadb -Date 20250723 -DateTo 20260723 -ChunkDays 7
```

前タスクの4パターン診断結果は以下のとおり。

`--diagnose-style-advantage`は予測/実績RPCI × 予測/確定脚質の4パターンを比較し、
`--venue-code`で競馬場別に絞り込める。2025年後半・2026年前半は正方向だったが、2026年7月だけ逆転。
福島は想定RPCIが主因、函館・小倉は確定値同士でも逆転した。短期標本のため本番係数は変更していない。

今回の検証は関連単体31 passed、Ruff成功、API全体62ファイルのmypy strict成功。API非統合全体は
485 passed / 3 failed / 22 deselected。失敗3件は既存のログ捕捉テストで、単独再実行は3 passed。
実DB1レースで`--validate-style-advantage --output`のJSON生成も成功し、一時ファイルは削除済み。

前セッションの検証は関連単体テスト29 passed、Ruff成功、対象2ファイルと
API全体62ファイルのmypy strict成功。API非統合全体は483 passed / 3 failed / 22 deselectedで、失敗3件は
既存のログ捕捉テストが全体実行時だけ`caplog`を取得できないテスト順序依存。3件の単独再実行は全件成功。
今回の変更対象テストに失敗はない。

`/health`はDBに依存しないlivenessとして維持し、`/ready`はDB接続とSQLAlchemy ORMが必要とする
全テーブル・列を検査する。不足時は503と`schema_outdated`を返す。Webは一覧APIが500になった場合だけ
`/ready`を取得し、スキーマ不足なら`python -m alembic upgrade head`、DB停止ならPostgreSQLと
`DATABASE_URL`の確認を案内する。通常表示時の追加通信はない。

実DBではAlembic 003→004を適用済みで、`/api/v1/races/board?date=2026-07-26`とWebトップの
200応答を確認した。前タスクで`RaceRepository`へ追加した`delete_entries_not_in`を
`_AsOfRaceRepository`にも委譲し、API全体mypyを0エラーへ戻した。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/infrastructure/database/readiness.py`,
`apps/api/src/pci/presentation/routers/health.py`, `apps/web/src/lib/apiError.ts`,
`packages/api-client/src/index.ts`, `docs/DECISIONS.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q`、
`cd ../.. && npm test --workspace=@pci/web`。

テスト結果: API非統合482 passed / 22 deselected、readiness PostgreSQL統合1 passed、関連33 passed、
Web71 passed、API Ruff、API全体mypy strict（62ファイル）、api-client/Web typecheck、Web build成功。
import-linterはローカルPythonに未導入のため未実行。既知の機能不具合はない。

---

### 直前タスク（成績未取り込みと出走馬スナップショット不整合の修復）

根本原因は、特別登録の仮馬番を確定出馬表で完全置換せず、結果だけを馬番で重ねていたこと、
JV障害コードを30番台と誤認していたこと、古い取り込みが誤った開催回・開催日次のレースキーを
生成していたことだった。確定出馬表の完全置換、結果前の出馬表再登録、特別登録の上書き防止、
JRA外・海外・障害の除外、`--only-incomplete`限定修復を実装した。

実DBは未取り込み343件から0件へ修復済み。`2026071910020811`は18頭・17頭着順反映、
`2026071910020801`は障害・11頭へ修正した。限定同期は310レース成功、11レース失敗。
失敗は距離0の海外行または確定出馬表を再構成できない行で、未取り込み警告には残っていない。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/application/race_use_cases.py`,
`apps/api/src/pci/infrastructure/repositories/race_repository.py`,
`apps/ingestion-worker/src/ingestion/batch.py`,
`apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`, `docs/DECISIONS.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と
`cd ../ingestion-worker && python -m pytest -q`。

未完了・既知事項: SQL統合テストはDocker依存のため今回未実行。worker全体Ruffには既存の
`windows_client.py`、`locate_corners.py`、`test_batch_e2e.py`等の違反が残る。API全体mypyは
Python 3.11設定とローカルNumPy 3.12型定義の不整合で停止するため、変更対象4ファイルだけ成功確認した。

---

### 直前タスク（今後のレース予想の事前生成）

`PrecomputeUpcomingForecastsUseCase`と認証付き`POST /internal/ingest/forecasts/precompute`を追加した。
workerには`--step forecasts`を追加し、`run_mykeibadb_full_sync.ps1`がentries、results、
special-entriesの後に実行する。対象は日本時間の今日以降、`status=entries`、出走馬ありのレースだけ。
過去レースへの後付け予想は行わない。ボードAPIのmart欠損時フォールバックは維持している。

テスト結果: API非統合472 passed、worker全体194 passed、Web68 passed/build成功、API Ruff成功、
変更対象APIのmypy strict、api-client/Web typecheck成功。worker全体Ruffは既存18件、全体mypyは
既存4件（`batch.py`のマスタ変数型）で失敗するが、今回対象のRuffは成功。

Claude Codeが最初に確認するファイル:
`apps/api/src/pci/application/forecast_precompute_use_cases.py`,
`apps/api/src/pci/presentation/routers/ingest.py`,
`apps/ingestion-worker/src/ingestion/batch.py`,
`apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`, `docs/DECISIONS.md`, `tasks/current.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と
`cd ../ingestion-worker && python -m pytest tests/test_ingest_api.py tests/test_batch_e2e.py -q`。

未完了・既知事項: 事前生成は同期HTTPリクエスト内で直列実行する（worker側タイムアウトは5分）。
今後レースが大幅に増えて5分を超える場合はジョブキュー化する。ローカル既存DBでは前タスクのmigration適用のため
API起動前に`cd apps/api && alembic upgrade head`が必要。

---

### 直前タスク（取り込みデータ完全性監視）

`GET /api/v1/ingest-status` は従来のバッチ成否・鮮度に加え、日本時間の前日以前で
`races.status=entries` のまま残るレースを集計する。Webトップは件数を警告し、代表20件への
リンクを表示する。取り込みログが無い環境でも、未取込レースがあれば警告する。

暫定条件は「前日以前かつentries」で、当日開催分は除外する。障害競走等の恒常的な誤警告が
確認された場合のみ、対象種別または猶予日数を追加する。現時点で既知の機能不具合はない。

テスト結果: API非統合447 passed、関連SQL integration 1 passed（残り18件は未実行）、Web66 passed、ruff clean、
Web typecheck/build成功。mypyはローカルNumPy型定義がPython 3.11設定で解釈できず依存解析前に停止。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/application/ingest_status_use_cases.py`,
`apps/api/src/pci/infrastructure/repositories/race_repository.py`, `apps/web/src/lib/ingestStatus.ts`,
`tasks/current.md`。最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と `npm test --workspace=@pci/web`。

---

### 以前のタスク（AbilityWeights比較CLI）

`--compare-ability-weights`で検証用4候補を同一レース集合に適用し、統合順位の3指標と
現行差をCLI/JSONに出力する。本番重みは書き換えず、実DBでの再現性確認後に別途判断する。

gradeはJRA-VAN公式コードをRA `GradeCD[615]`から読み、ability-v3のクラス補正で優先利用する。
馬体重は既存`race_entries.weight`へ、results単独再取込でも確定値を更新する。体格の大小は能力へ
加点せず、バックテストへ統合順位の比較指標を追加した。

Codex は `tasks/current.md` の最優先候補として「バックテスト結果のJSON保存」に着手し、
ローカルで `144ebfd feat(backtest): export reports as json` を作成した。しかし push 前に
`origin/claude/sweet-einstein-ilnaov` が16コミット進んでおり、その中の `03bc005 feat(backtest):
persist backtest reports to JSON via --output` が同じ目的をより新しい文脈で実装済みだった。
そのため `git merge origin/claude/sweet-einstein-ilnaov` の競合解消では、バックテストJSON保存関連
ファイルと各ドキュメントについて**リモート版を採用**し、後続のClaude Code変更を上書きしない方針にした。
競合マーカーは残っていない。

**直前セッションの要約**: (1) 確定成績未反映の件は**解決**。診断で「解析は正常（453件解析可）」と特定し、
`batch.py`が`record_results`失敗をexit 0に握りつぶしていた欠陥を可視化（件数ログ常設）。ユーザーが
最新コードでresultsステップを再実行→全レース送信成功しアプリに反映。(2) ユーザーが選んだ改善
「**統合順位予想（展開＋能力）**」を Phase1（ability-v1 × integrated-v1）→ ユーザーFB受けてUI刷新
（◎○▲△の印を廃止しタグ＋順位主役へ）→ Phase2（人気・本賞金の永続化でability-v2）まで実装済み。
詳細は下記「完了した作業」0.〜2.、`docs/DECISIONS.md` 2026-07-21（2件）。

（以下は本セッションに至るまでの経緯。）

ユーザーから実利用のフィードバックを受け、2点対応した:
① 展開分析の脚質別有利度が高止まりして差が出ない（`3d3131e` で修正済み）。
② 展開恩恵馬のピックアップに加えて絶対能力も加味した順位予想が欲しい → ユーザー判断で保留
（`tasks/backlog.md` B節、能力指数の算出方法自体の模索が必要なため）。

保留②を受け「他に実施すべき改善」の相談から**推奨1: データ取り込みの監視・鮮度表示**を実装（`2b83d75`）。
続けて「次の推奨する選択肢」として `tasks/backlog.md` C節の技術的負債に順に着手し、
(a) mypy --strict 全体エラーが誤情報だったと判明・訂正（`9ed1ff7`）、
(b) 旧handoffファイルの整理（`f2a8ea6`）、
(c) JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化（`24731ed`）を行った。

その後ユーザーから新規の不具合報告が2件続いた。
1件目: 「月曜なのに土日の開催結果と来週の特別登録馬が反映されていない」。調査の結果、
自動同期スクリプトが`--step special-entries`を一度も呼んでいなかったバグを発見・修正
（`c49ce05`）。土日結果側は別原因の可能性が高く、このクラウド環境からは診断できないため
ユーザーへ確認依頼中。
2件目: スクリーンショット2枚で「①一部のレース結果（9R〜11R）が反映されていない」
「②枠順確定前のレースなのに馬番が出ている」を報告。②はコードで原因を特定・修正
（`e2f0b3c`）。①はアプリ層のバグではなく取り込みギャップの可能性が高いと判断したが、
このクラウド環境からは特定できずユーザーへ確認依頼中、として一旦終了。

その後、ユーザーがWindows実行機で①の指示どおり手動再同期を実施した結果、状況がより
深刻かつ明確になっていたと判明: 実際は「9R〜11Rだけ」ではなく**2026-07-12以降（7/12・
7/18・7/19の全開催日）確定成績が一切反映されていない**一方、**7/25・26の特別登録は
正常に反映されている**とのユーザー報告。「取り込みは動いているが確定成績の検出だけが
機能していない」という手がかりから`mykeibadb_client._build_se_record()`のDATA_KUBUN
列の扱いに仮説を立て修正した（`af922a5`）。

**しかしユーザーが再pull＆再同期しても改善せず、DATA_KUBUN仮説は空振り**と判明。
同期ログは全ステップ exit code 0（＝件数ではなく「クラッシュしていない」だけ）で、
原因層すら特定できない状態だった。そこで方針を「推測で直す」から「測って切り分ける」へ
転換し、(1)`batch.py`に件数ログを常設、(2)切り分け診断ツール`ingestion.diagnose_results`を
新設、(3)`DaysBack`既定を7→10に修正した（下記「完了した作業」2.）。
その後の診断で解析は正常と判明し、送信段階の可視化で**解決に至った**（→「完了した作業」2.）。

---

## 完了した作業（直近セッション）

0H. **成績未取込警告から安全な手動再同期コマンドを提示**（本セッション）
   - domain/infrastructure: `RaceCompletenessRepository`へ最古未取込日取得を追加し、SQLの`min()`で
     全件をロードせず集計する。代表20件の範囲外も再同期対象に含められる。
   - application/API: 標準10日と最古未取込日までの日数の大きい方を
     `recommended_sync_days_back`として返す。OpenAPI/api-client型を再生成した。
   - Web: 警告・失敗・鮮度低下時だけ、リポジトリ直下から実行するPowerShellコマンドを提示。
     コピー成功・失敗をアイコン状態で伝える。正常時は表示しない。
   - 安全性: APIからWindowsプロセスは起動しない。直接起動は認証・ジョブキュー・多重実行防止が
     整うまで不採用とした。
   - テスト: API非統合464 passed、関連12 passed、Repository統合1 passed、Web67 passed、
     ruff、変更対象mypy、api-client/Web typecheck、Web build成功。

0G. **展開コメント生成をゼロコスト既定モードへ変更**（本セッション）
   - config: `COMMENT_GENERATOR_MODE`を`rule | gemini`のLiteral設定として追加。既定は`rule`で、
     未知の値はPydantic設定読込時に拒否する。
   - DI: APIキーの有無だけではGeminiを選ばず、`gemini`モードとキーが両方ある場合だけ
     `GeminiCommentGenerator`を生成する。キー欠損・初期化失敗はルールベースへ縮退する。
   - テスト: API非統合463 passed、関連29 passed、ruff、変更対象mypy strict成功。
     全体mypyは既知のNumPy型定義/Python設定不整合、import-linterは未導入のため未達。
   - 未確認・既知の不具合: なし。外部APIは意図的に呼び出していない。

0F. **Gemini既定モデルを3.5 Flashへ移行し、環境変数化**（本セッション）
   - config: `Settings.gemini_model`を追加。既定は`gemini-3.5-flash`、環境変数
     `GEMINI_MODEL`で上書き可能。`.env.example`にも設定例を追加した。
   - infrastructure/DI: `GeminiCommentGenerator`へ設定値を渡し、`reasons`には実際に
     使用したモデル名を記録する。Gemini版の世代を`comment-gemini-v3`へ更新した。
   - フォールバック: `GEMINI_API_KEY`未設定・呼出失敗時は従来どおり`comment-v2`を使用する。
   - テスト: API非統合457 passed、関連23 passed、ruff、変更対象3ファイルのmypy strict成功。
   - 未確認: 実API呼び出しはAPIキーと外部費用を使わないため未実施。HTTP経路はモックで検証済み。

0E. **枠順未確定時の展開コメント馬番号表示を修正**（本セッション）
   - domain: `horse_number_label.py`を追加し、確定時「N番」・未確定時
     「登録順 N（馬番未確定）」を共通化。scenario・commentaryの自然文へ適用。
   - application: `predict_formation()`の成否を枠順確定の単一判定とし、scenarioと
     `ForecastCommentInput.horse_numbers_confirmed`へ渡す。
   - infrastructure: Geminiプロンプト内の展開恩恵馬も同じ表示へ統一。
   - version: `comment-v2` / `comment-gemini-v2`。API公開スキーマ変更なし。
   - テスト: API非統合454 passed、関連74 passed、ruff、変更対象mypy strict成功。
   - 既知の不具合: なし。import-linter未導入と全体mypyのNumPy型定義問題は環境起因。

0D. **LightGBM Windows改行破損修正・AbilityWeights実DB採用判断**（本セッション）
   - `.gitattributes`: `apps/api/models/*.txt text eol=lf`を追加。Git blobとWindows作業ファイルの
     サイズ差（芝398,640→400,397 bytes）からCRLF変換による`tree_sizes`破損を特定した。
   - `lgbm_forecaster.py`: 読込前にCRLFをLFへ自己修復し、既存cloneも再checkout不要で救済。
     split/unifiedモデルの読込失敗を黙殺せず、フォールバック先と例外を警告する。
   - `TestCommittedModels`: 追跡中の芝・ダートモデルを実ロードし、両コースを予測する回帰テスト。
   - 実DB比較: 2025-07-01〜12-31を212レース、2026-01-01〜07-21を97レースで評価。
     全3指標が両期間で改善する候補はなく、`DEFAULT_WEIGHTS`は変更しないと決定。
   - 仮実装・未確定仕様: なし。成分重み以外の減衰・正規化定数は引き続き未確定。
   - 既知の不具合: なし。mypyのみローカルNumPy型定義とPython 3.11設定の不整合で、
     対象コードの型解析前に停止する。
   - テスト: API非統合449 passed、LightGBM関連31 passed、ruff、実DBバックテストCLI成功。

0C. **取り込み監視をデータ完全性へ拡張**（本セッション・OpenAI Codex）
   - domain: `RaceCompletenessRepository`を追加。既存の汎用`RaceRepository`は変更せず、
     状態監視に必要な読み取りだけを分離した。
   - infrastructure: `SqlAlchemyRaceRepository.count_incomplete_past_races()` /
     `find_incomplete_past_races()`を追加。日本時間の当日より前かつ`RaceStatus.ENTRIES`を対象に、
     件数と新しい順の代表20件をDBで取得する。
   - API: `IngestStatusOutput` / `IngestStatusSchema`へ`has_incomplete_races`、
     `incomplete_race_count`、`incomplete_races`を追加し、OpenAPIとapi-client型を再生成。
   - Web: `ingestStatusMeta()`で直近失敗を最優先、次に成績未取込、次に鮮度低下を表示。
     `IngestStatusBanner`の開閉領域から対象レースの予想画面へ移動できる。
   - 仮実装・暫定値: 詳細上限20件。当日開催分は正常な結果待ちとして除外。障害競走等の
     個別除外は未実装で、誤警告が確認された場合のみ見直す。
   - 既知の不具合: なし。Dockerを使うSQL実装用の`TestFindIncompletePastRaces`は実行済み。
     その他のintegration 18件は今回の対象外として未実行。
   - テスト: API非統合447 passed、関連SQL integration 1 passed、Web66 passed、ruff、
     Web typecheck/build成功。mypyのみローカルNumPy型定義とPython 3.11設定の不整合で停止。

0B. **AbilityWeightsの同一期間比較CLI**（本セッション・OpenAI Codex）
   - `DEFAULT_ABILITY_WEIGHT_PROFILES`に現行・近走のみ・近走重視・市場支持重視を定義。
   - `compare_ability_weight_reports()`で現行差を計算し、`format_ability_weight_comparison()`と
     `ability_weight_comparisons_to_dict()`でCLI/JSONへ出力。
   - `scripts/backtest_forecast.py --compare-ability-weights`を追加。現行レポートは再利用し、
     残り3候補だけを追加実行する。候補は自動採用しない。
   - API unit+contract 444 passed（関連は40 passed）、変更対象Ruff、mypy strict 58ファイル、
     CLI `--help`成功。実DBでの実行は未実施。

0A. **統合順位予想 Phase 2完成（grade・確定馬体重・検証指標）**（本セッション・OpenAI Codex）
   - ingestion: RA `GradeCD[615]`を公式コードから名称化。mykeibadb合成RAにも同位置へ書き込み。
     SE確定レコードの`BaTaijyu[324:327]`をresults送信へ追加し、gradeとともにAPIへ渡す。
   - API: `ResultBody.grade` / `ResultItem.body_weight`を追加。結果登録時に`races.grade`と既存
     `race_entries.weight`を更新。新規migrationは不要。
   - ability-v3: gradeをクラス係数へ優先利用し、欠損時のみrace_classへ縮退。馬体重は能力加点しない。
   - backtest: 統合順位の1位馬勝率・1位馬好走率・TOP3好走捕捉率をテキスト/JSONへ追加。
     `ForecastBacktester`へ`AbilityScorer`注入点を追加し、候補重みを同一期間で比較可能にした。
   - 検証: API unit+contract 440 passed、ingestion 191 passed、Web 65 passed、変更対象Ruff、lint-imports、
     api-client/web typecheck、Web build成功。mypy strictは既知の`lgbm_forecaster.py:58 unused-ignore`のみ。

0. **統合順位予想: UI刷新（印→タグ）＋ Phase2（人気・本賞金→ability-v2）**（前セッション・`7997931`）
   - **UI（ユーザーFB「印よりタグが分かりやすい・順位を明確に」）**: `IntegratedRankingView` 刷新。
     ◎○▲△の印を廃止、総合順位（1位…）を主役に、分類は言葉タグ（本命/対抗/穴（妙味）/人気でも注意/
     能力上位・中位/展開が向く・向きにくい）。プレゼン層のみ（`8cda3bb` のドメイン/スキーマは不変）。
   - **Phase2 データ永続化**: 人気(TANSHO_NINKIJUN)・獲得本賞金(KAKUTOKU_HONSHOKIN)を追加。経路=
     mykeibadb列 → SE合成の**予約offset**（jv_spec `Ninki`[541:543]/`Honsyokin`[543:552]・mykeibadb合成
     専用・未検証。jvlink実COMでは書かれず読み側で弾く）→ `parse_se_result`（妥当性ゲート）→ Ingest API
     （ResultItem/ResultInput）→ `RaceEntry`＋ORM＋repository＋**migration 003** → `race_entries.popularity/
     prize_money`。ingest_api の results payload にも追加。
   - **ability-v2**（`domain/pace/ability.py`）: form(近走着順×クラス)0.55＋本賞金(対数正規化)0.30＋
     人気0.15 を新しさ加重ブレンド。**データ無し成分は除外し重み再正規化 → 旧データは form のみ＝v1相当へ
     安全に縮退**（再取込まで壊れない）。本賞金が「入着時の稼ぎ＝相手クラス」を連続量で捉え、grade未永続化
     によるクラス係数 best-effort の限界を緩和。🧪重みは §9-16。
   - **運用（ユーザー作業・必須）**: `alembic upgrade head`（003）＋過去 results 再取込で人気/賞金が埋まる
     （`MANUAL_SYNC_GUIDE §7.5`）。未実施でも縮退動作で壊れない。
   - 検証: API 436 passed、ingestion 185 passed（+2 round-trip）、Web 65 passed・typecheck・build clean、
     ruff/lint-imports/mypy clean（既存 lgbm・ingestion tuple-concat debt のみ・新規0）。OpenAPI/schema.d.ts 再生成。

1. **統合順位予想（能力×展開）Phase1 を実装**（本セッション・`8cda3bb`）
   - 経緯: ユーザー要望「展開＋絶対能力の統合順位予想」（2026-07-12保留）を再開。独断で仕様化しない
     方針に従い、データ範囲と統合の見せ方をユーザーに選択提示 → **現データのみでPhase1** ＋
     **2軸分類（本命/対抗/穴/危険）** を採用（`docs/DECISIONS.md` 2026-07-21）。
   - domain（純粋・reasons・model_version付き）:
     - `pace/ability.py`（ability-v1）: 各近走 = 出走頭数正規化した着順 × クラス係数、を新しさ加重
       平均（直近5走）。0〜100の内部score。🧪仮係数は `AbilityWeights`。
     - `pace/integrated_ranking.py`（integrated-v1）: 能力のレース内相対順位（上位/中位/下位/評価難）
       × 展開適性(合致/中立/不利)で ◎本命/○対抗/△危険/▲穴/無印 に分類。表示順も2軸から決定的に導出
       （恣意的な重み合算は不採用＝ユーザー選択）。
   - 結線: `forecast_use_cases`（`_build_ability_score` で近走+過去レースからability構築→`build_
     integrated_ranking`）、`dto.py`（`IntegratedRankingOutput`/`IntegratedEntryOutput`）、
     `schemas.py`（同Schema）、OpenAPI再生成（`openapi.json`+`schema.d.ts`）、`api-client/src/index.ts`。
   - web: `IntegratedRankingView.tsx`（新規）を `RaceForecastDashboard` の隊列予想の前に配置。
     ◎○▲△・能力上位/中位・展開が向く/向きにくいを**言葉と記号**で表示（PCI/PAI等の実数値は非表示）。
   - 当時の既知の限界: `grade`未永続化で、クラス係数は`race_class`文字列のbest-effortだった。
     **この制約は本セッションのability-v3で解消済み**（上記0A）。
   - 検証: **apps/api はこの新コンテナで環境未構築だったため `python -m venv .venv && .venv/bin/pip
     install -e ".[dev]"` で構築**（下記「注意事項」）。API unit+contract 432 passed（+新規domain16・
     contract1）、Web 65 passed、api/web typecheck・build・ruff・lint-imports・mypy --strict すべてclean
     （既存の `lgbm_forecaster.py:58` unused-ignore 1件のみ＝当環境のlightgbm差異による既存・無関係）。

2. **【解決】確定成績が2026-07-12以降反映されなかった件**（本セッション）
   - 診断ツール`diagnose_results`で「**解析は正常（453件解析可・DATA_KUBUN='7'）**」と判明 → 原因は
     解析より下流と特定。`RecordRaceResultUseCase`はレース未登録で例外を投げるが、`batch.py`の
     `ingest_results`が**per-raceでcatchしてexit 0**にしていた（全送信失敗でも「成功・0件」に見える）。
   - 送信成功/失敗の件数ログ（「確定成績送信 …: 成功 X / 失敗 Y」・全滅時WARNING）を常設し可視化。
     ユーザーが最新コードで results ステップを各日付に再実行 → **全レース送信成功しアプリに反映（解決）**。
   - 恒久対策: 件数ログ・`diagnose_results`（RA突き合わせ含む）・`DaysBack`既定7→10。再発時は即切り分け可。
   - 残: 障害競走の成績が別途未反映（ユーザー保留）。第1仮説のDATA_KUBUN修正(`af922a5`)は空振りだが
     単調・無害のため残置。

3. **展開恩恵馬カードが枠順未確定の馬番を確定情報のように表示するバグを修正**（`e2f0b3c`）
   - ユーザー報告（スクリーンショット）: 枠順確定前のレースなのに「展開恩恵馬TOP5」等に馬番が出ている。
   - 原因: `formation-v1`（隊列予想）は`frame_no`で確定/未確定を判定し未確定時は`formation: null`に
     する設計だったが、同じ画面のPAI系出力`HorseFitOutput`にはそもそも`frame_no`が無く、
     この判定が一切されていなかった。特別登録段階の`horse_no`は`ingest_entries()`がUMABAN=0時に
     割り当てる暫定連番で、公式馬番ではない可能性がある。
   - 対応: `HorseFitOutput`/`HorseFitSchema`に`frame_no`を追加（`FormationHorseSchema`と異なり
     `ge=1,le=8`制約なし。0=未確定が正常値）。`forecast_use_cases.py`で`RaceEntry.frame_no`から
     供給。OpenAPI再生成。web側`lib/pace.ts`に`horseNumberLabel()`を新設し、`frame_no>0`なら
     「馬番 N」、`frame_no=0`なら「登録順 N（馬番未確定）」を返す。`RaceForecastDashboard.tsx`
     （TOP5カード・評価下げカード・先導候補チップ）・`HorseFitTable.tsx`・`app/page.tsx`
     （トップ画面の中心候補プレビュー）の計5箇所を統一。
   - PAIスコア自体は枠順確定前でも意味があるため、formation-v1のように出力ごと非表示にはせず、
     ラベルの誠実さだけを是正する方針とした（`docs/DECISIONS.md`参照）。
   - **後続対応**: `scenario.py`を含む自然文コメントの同種問題は2026-07-22の
     `comment-v2`で解決済み。
   - 検証: API 415 passed（+1）、Web 65 passed（+2）、ruff/mypy --strict/lint-imports/
     typecheck/build すべてclean。

4. **自動同期が来週の特別登録を一度も取り込んでいなかったバグを修正**（`c49ce05`）
   - ユーザー報告「月曜なのに土日の結果・来週の特別登録馬が未反映」を調査。
     `run_mykeibadb_full_sync.ps1`（Task Scheduler「PCI_Sync_Mykeibadb」金/土10:00・日18:00が実行）は
     `batch.py --step entries`/`--step results` のみを呼んでおり、`--step special-entries`
     （mykeibadbの`TOKUBETSU_TOROKUBA`系という**別テーブル**を読む独立ステップ）を一度も
     呼んでいなかったと判明。`setup_task_scheduler.ps1`自身のdocstringは「日曜18:00は来週の
     重賞特別登録取り込みも兼ねる」と明記しており、実装漏れと判断（`docs/DECISIONS.md`参照）。
   - 対応: `run_mykeibadb_full_sync.ps1`に3番目の呼び出し（同じ過去7日〜未来14日の日付窓で
     `-Step special-entries`）を追加。`sync_mykeibadb.bat`・`MANUAL_SYNC_GUIDE.md`（手順・
     注意書き・6.8節トラブルシューティング新設）・`docs/SPEC.md §6`・`docs/DECISIONS.md`を更新。
   - `--step special-entries`自体はbatch.py/mykeibadb_client.pyで既に実装・単体テスト済みの
     機能で、`run_batch.ps1`のリトライ/Webhook通知も汎用対応済みだったため、追加は自動実行
     スクリプトへの呼び出し1行の低リスクな変更。
   - **未解決**: 「土日の確定成績が反映されていない」側は自動実行の対象内（`--step results`）
     のはずで、「取りこぼし」ではなく「実行自体の失敗/未発火」の可能性が高いが、Task Scheduler
     実行履歴・ログ・MySQL80サービス状態はこのクラウド環境から確認できないため、ユーザー自身の
     診断が必要（`MANUAL_SYNC_GUIDE.md §6.8`に診断手順を用意、ユーザーへ確認依頼中）。
   - コード修正のみでは今週分の取りこぼしは遡って埋まらないため、`--step special-entries`の
     手動実行コマンドを別途ユーザーへ案内。

5. **JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化**（`24731ed`）
   - `tasks/backlog.md` C節に着手。`apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` を新規作成し、
     `dump_records.py`→`verify_layout.py`（アンカー検証→フィールド目視確認）→`locate_haron.py`/
     `locate_corners.py`（新オフセット特定）→`jv_spec.py`更新→テスト更新→記録、という一連の手順と
     安全策（1レースだけでCONFIRMED昇格しない等）を明文化。
   - 調査で判明: UM/KS/CH（`master_parsers.py`）は Ver.3.0.0→Ver.4.9 の実データ差分
     （ketto_num直後に日付フィールド群24byte追加、名前位置シフト）を既に確認・反映済みという実例が
     存在した。一方RA/SE（`jv_spec.py`）はREADME.md/common.pyが「Ver.3.0準拠」と書いたままで、
     実際にどのバージョンの出力を元に校正したかは未確認（独断で確定せず`docs/SPEC.md §9`-8に記録）。
   - `README.md`・`docs/SPEC.md`（§6, §9-8）から新ガイドへの相互参照を追加。コード変更なし。
   - 未完了: 実際の再検証実施はWindows実行機（JV-Link必須）が必要なため、このセッションでは
     手順の明文化のみ。実施自体は引き続き未着手。

6. **旧handoffファイルの整理**（`f2a8ea6`）
   - `docs/handoff-claude-code-2026-06-25.md` を精査。全項目が (a) 現構成と食い違う誤情報
     （`domain/services.py`・`infrastructure/repositories.py`は現存しない旧パス、
     「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
     （ローカル起動→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
     同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）と判明。
     「吸収すべき未収録の情報」が残っていなかったため削除（Git履歴には残り復元可能）。
   - 他ドキュメントからの参照は `tasks/backlog.md` のみだったことを確認済み（削除後に更新）。

7. **mypy --strict 全体エラーは誤情報だったと判明・訂正**（`9ed1ff7`、コード変更なし）
   - `tasks/backlog.md` C節「mypy src/ --strict を全体で通すためのスタブ導入」に着手する過程で、
     `python -m mypy src/ --strict` を実行したところ **56ファイル全体で0エラー**（キャッシュ削除後も再現）。
   - 原因: 素の `mypy` コマンドが `/root/.local/bin/mypy`（`uv tool` 等で別途インストールされた、
     プロジェクトの依存関係が入っていない隔離環境）を指しており、fastapi/sqlalchemy/pydantic
     （実際はいずれも py.typed 同梱で型情報あり）を「見つからない」という誤エラーを出していた。
     `pytest`と全く同じ根本原因（前セッションで発見済みの問題と同型）。
   - 対応: `CLAUDE.md`, `AGENTS.md`, `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`,
     `apps/api/README.md`, `tasks/backlog.md` の「環境要因・コード欠陥ではない」という誤記載を
     すべて訂正し、`python -m mypy src/ --strict`（全体0エラー）を正しい実行方法として明記。
   - Definition of Done も「domain・applicationは0エラー」から「全体で0エラー」へ引き上げ
     （実態がその基準を既に満たしていたため）。
   - 検証: `rm -rf .mypy_cache && python -m mypy src/ --strict` → Success: no issues found in 56 source files。

8. **データ取り込みの鮮度監視**（`2b83d75`）
   - 背景: `ingest_log` は書き込み専用で、自動同期が静かに失敗し続けても気づけなかった。
   - 対応: 新規 `domain/ops/ingest_log.py`（`IngestLogRepository` Protocol + 純粋関数
     `evaluate_freshness()`）。判定は「直近試行の失敗有無」「直近成功からの経過日数
     （暫定閾値 `STALE_AFTER_DAYS=4`）」のみで、Task Schedulerの具体的cronはコードに埋め込まない。
     `GET /api/v1/ingest-status`（公開GET、`/internal/ingest/*`の認証とは別）を新設し、
     web トップに `IngestStatusBanner`（正常時は控えめ、鮮度低下・失敗時のみ目立つ配色、
     失敗一覧は開閉式で最大5件・エラー要約200文字まで）を追加。
   - ログが1件も無い環境（開発/fixture等）は `has_history=False` とし「異常」ではなく
     「監視対象外」として扱い、誤警告を防ぐ。
   - **未実施（ユーザー環境でのみ確認可能）**: `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に
     届くかの実地確認。再同期コマンド提示は0Hで実装済み。APIからの直接起動は安全要件未整備のため不採用。

9. **脚質別有利度の修正（style-advantage-v1）**（`3d3131e`）
   - 原因: web が「その脚質の最大PAI」を有利度に流用しており、スコアが60〜96に高止まり。
   - 対応: `domain/pace/style_advantage.py` 新設。想定RPCIの中立点（classify_pace と同じ
     rule-v4 閾値の中点: 芝50/ダート43）からの乖離を 50=互角の対称スコア（0〜100）へ写像。
     逃げ・追込は増幅1.2、逃げ候補2頭以上で逃げのみ競合減点。reasons/model_version 付き。
   - `StyleAdvantageWeights` は🧪仮係数（`docs/SPEC.md §3.4/§9`-11、`docs/DECISIONS.md` 2026-07-12）。

9a. **脚質別展開有利度の実DB検証基盤**（`66568ad`）
   - `ForecastBacktester`へ有利群・不利群の好走率、リフト、好走率差、point-biserial相関とJSON明細を追加。
   - `backtest_forecast.py --validate-style-advantage`は確定RPCI・確定脚質を使い、係数の方向性だけを
     高速診断する。`--output`で診断サマリをJSON保存できる。本番予測精度として扱わない。
   - 実DB診断（各1000レース）: 芝7952頭で有利26.4%／不利19.3%（差+7.1pt）、
     ダート8618頭で33.0%／14.0%（差+19.0pt）。ルール方向は妥当。
   - 予測込み（各100レース）: 芝17.6%／27.8%（差-10.2pt）、ダート28.5%／19.7%（差+8.8pt）。
     芝だけ逆転するため`StyleAdvantageWeights`は変更せず、想定RPCIと脚質予測の切り分けを残した。

9b. **脚質別展開有利度の誤差要因診断**（本セッション）
   - `ForecastBacktester.diagnose_style_advantage()`と`--diagnose-style-advantage`を追加。
   - 4パターンで共通して脚質を判定できた馬だけを使い、母集団差による誤読を防ぐ。
   - `--venue-code`で開催場別診断、`--output`でJSON保存が可能。前セッションで混入した
     `args.output.write_text`（`str`に対する誤呼び出し）も通常のJSON writerへ修正。
   - 実測値は`docs/SPEC.md §3.4`と`docs/DECISIONS.md` 2026-07-23を参照。

10. **バックテスト結果のJSON保存**（`03bc005`）
   - `report_to_dict()` + `--output <path>`。混合＋track別内訳をJSON保存。print出力は不変。

11. **Codex引き継ぎ内容の検証**（`af66e8f`、ドキュメントのみ）
   - ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従（無傷）。
   - Codexの実装3件をコードレベルで検証し、テストを独立再実行。重大な不整合なし。

12. **混在型脚質の距離対応予測**（`2b083ba`、Codex実装・検証済み）
   - 直近20レース266頭を調査し、旧自在139頭のうち99頭が60%未満の混在、40頭が履歴なしと確認。
   - 明確な `running-style-v1` 判定は維持し、混在型だけ `running-style-v2-distance` で再判定。
   - 過去5走の4角位置、対象距離との距離差、近走順を使用。先行・差し同数時の距離規則を追加。
   - 予想日以後の成績を参照しないよう、履歴取得に開催日前カットオフを明示。
   - 同じ266頭で自在を139頭（52.3%）から40頭（15.0%）へ削減。履歴なしは参考のまま維持。
   - API 380件、Web 55件、ruff/mypy/import-linter/typecheck/buildがすべて成功。

13. **枠順確定後の隊列予想**（`c679e09`、Codex実装・検証済み）
   - `domain/pace/formation.py` に枠順確定判定と formation-v1 を追加。
   - 全馬の枠番が1〜8、馬番が正かつ一意の場合のみ予想し、特別登録（frame_no=0）は `null`。
   - 脚質70%・近走の1角（欠損時4角）位置30%で先頭/好位/中団/後方へ配置。
   - 各馬に日本語の根拠と「高・標準・参考」の信頼度ラベルを付与。
   - OpenAPI/API Clientを再生成し、WebにJRA枠色の `FormationView` を追加。
   - 契約テストの予測器をルールベースへ固定し、WindowsのLightGBMネイティブabortを回避。
   - 実DBで entries 278件、枠順確定112件は生成、未確定166件は非生成を確認。

14. **レース分析UIの刷新**（`4d9e5b5`、Codex実装・検証済み）
   - `AppHeader` を追加し、全画面でブランドとレース一覧への導線を固定。
   - レース一覧を最大幅拡張し、統計、開催日カレンダー、日付・競馬場別レースを2カラム化。
   - 展開予想と確定後回顧へ共通のダークヒーローとエメラルドのアクセントを導入。
   - 予想サマリー、初心者向け解説、展開恩恵馬、評価を下げたい馬の視覚階層を整理。
   - 回顧画面は「PCI判定」を「ペース傾向」へ翻訳し、内部実数値を新たに露出していない。
   - モバイルでは1カラム、デスクトップでは一覧のカレンダーをstickyサイドバーとして表示。

以下は以前の完了作業:

15. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
   - `apps/api/src/pci/application/backtest.py` に純粋関数 `group_races_by_track(races) -> dict[str, list[Race]]` を追加。
   - `apps/api/scripts/backtest_forecast.py` に `_print_track_breakdown()` を追加。
     `--track-type` 未指定時、混合集計に加えて芝/ダート別の再集計も自動表示する。
   - 動機: コース混合のまま集計すると PAI の point-biserial 相関が希釈されて見える落とし穴が
     検証中に判明したため（`docs/adr/0005-rpci-forecast-strategy.md §5.4`）。
   - テスト: `apps/api/tests/unit/application/test_backtest.py::TestGroupRacesByTrack` 2件追加。
   - **既知のトレードオフ**: track別内訳は `ForecastBacktester.run()` を track ごとに**再実行**する
     （キャッシュ済みサンプルの再集計ではなく、予測をもう一度回す）。DB再クエリ（対象選定）は
     発生しないが、予測処理自体は2倍実行される。`--limit` が大きい（例: 2000+）場合は
     実行時間がおよそ2倍になる点に注意。
16. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
17. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
18. **`forecast_accuracy` の UI 表示**（`e65f919`）、**AI 引き継ぎ基盤整備**（`004aead`）、
    **予測フィードバックループ**（`9712fd2`）ほか、それ以前の完了作業は
    `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

- **確定成績未反映は解決済み**（上記「完了した作業」2.）。残る関連事項は障害競走の成績が別途
  未反映（ユーザー保留）のみ。
- **統合順位予想 Phase2・AbilityWeights比較CLI・実DB採用判断は完了**。残る検証は、
  実JV-Link COMにおけるGradeCD[615]および人気/賞金予約オフセットの確認（`tasks/backlog.md` B節）。
- **脚質別展開有利度の複数年・距離別比較は完了**。7月小倉芝1200mだけ`reference`表示とした。
  残る課題は、RA馬場状態の取り込み・バックフィル後の馬場別再検証と、福島の想定RPCI誤差の調査。
  `StyleAdvantageWeights`は未変更。
- **Windows実行機での実地確認が必要な残課題**（このクラウド環境からは検証不可）:
  `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に届くか。`special-entries`呼び出しを追加した
  自動同期スクリプト自体がWindows実行機で問題なく動くかも未確認。
- 画面からの安全な再同期コマンド提示は完了。直接実行ボタンは認証・ジョブキュー・多重実行防止が
  未整備のため意図的に実装していない。
- **JV-Data仕様追従の実施自体は未着手**（`apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md`で
  手順は明文化したが、実データ取得にはWindows実行機＋JV-Linkが必要でこのクラウド環境からは不可。
  RA/SEが実際にVer.3.0.0/Ver.4.9のどちらの出力を元に校正されたかも未確認のまま、`docs/SPEC.md §9`-8）。
- それ以外はなし。

## 現在止まっている箇所

**コード実装は停止していない。実DBバックフィルだけWindows実行機でのユーザー操作待ち。**
バックフィル前はWebトップの馬場情報未反映警告が出る想定で、完了後は件数0となり警告が消える。

---

## 次に実施すべき作業（候補・優先順位順）

ユーザーからの新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する。
**どれを選ぶかはユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針）。

0. **P2 実DBで馬場状態を1年分バックフィルし、馬場状態別に再検証**。
   Web警告内のコマンド、または上記`run_batch.ps1 -Step race-metadata`をWindows実行機で実行し、
   `/api/v1/ingest-status`の`missing_track_condition_count=0`とWeb警告消去を確認後、
   `python -m scripts.backtest_forecast --validate-style-advantage --track-type 芝 --venue-code 10
   --date-from 2025-07-01 --date-to 2026-07-31 --style-breakdown year
   --style-breakdown track-condition --style-breakdown distance`で欠損率と小倉芝1200mを確認する。
1. **P2 実JV-Dataの人気/賞金予約オフセット検証**。Windows実行機のJV-Link COMが必要。
   `JV_SPEC_MAINTENANCE_GUIDE.md`の手順に従い、実レコードの位置を確認してから正式化する。
2. **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・`RuleWeights`・`PaiWeights`・
   `FormationWeights`・`DistanceStyleWeights`・`STALE_AFTER_DAYS`・
   `AbilityWeights`の成分重み以外）
   - 実データ・実運用での検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行/
     しばらく運用→結果を分析」の進め方になる可能性が高い。着手前にどの定数を対象にするか確認する。
3. **Webhook通知のWindows実地確認**。`NOTIFY_WEBHOOK_URL`を設定し、失敗時に通知が届くか確認する。

**保留・確認待ちの項目**:
- APIからの直接再実行ボタン化 — 認証・ジョブキュー・多重実行防止・Windows接続方式が整うまで保留。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張（2026-07-11決定） — `forecast_accuracy` 蓄積が増える、
  またはダートの外れに偏りが見えた場合に再検討。

---

## 変更対象ファイル（直近セッション）

馬場状態欠損のデータ完全性監視と復旧導線:
- API: `application/dto.py`, `application/ingest_status_use_cases.py`,
  `domain/racing/repository.py`, `infrastructure/repositories/race_repository.py`,
  `presentation/schemas.py`
- Web: `apps/web/src/lib/ingestStatus.ts`, `apps/web/src/components/IngestStatusBanner.tsx`
- worker: `apps/ingestion-worker/scripts/run_batch.ps1`
- tests: API unit/contract/PostgreSQL integration、Web `ingestStatus.test.ts`
- generated: `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`
- docs/tasks: worker `README.md`、`docs/SPEC.md`、`docs/DECISIONS.md`、
  `docs/HANDOFF.md`、`tasks/current.md`、`tasks/backlog.md`

それ以前の直近セッション:

mykeibadb馬場状態・天候の取り込みとバックフィル:
- API: `application/race_use_cases.py`, `presentation/routers/ingest.py`
- worker: `models.py`, `client/base.py`, `client/mykeibadb_client.py`, `ingest_api.py`, `batch.py`
- tests: APIのrace use case/ingest契約、workerのmykeibadb/API/batch E2E

安全な手動再同期支援で変更したファイル:
- API: `domain/racing/repository.py`, `application/dto.py`, `application/ingest_status_use_cases.py`,
  `infrastructure/repositories/race_repository.py`, `presentation/schemas.py`
- Web: `apps/web/src/lib/ingestStatus.ts`, `apps/web/src/components/IngestStatusBanner.tsx`,
  `apps/web/src/components/IngestRecoveryCommand.tsx`
- 型: `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`
- テスト: API unit/contract/integrationの取り込み監視・Repositoryテスト、
  `apps/web/src/lib/ingestStatus.test.ts`
- 文書: `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`,
  `docs/DECISIONS.md`, `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

Geminiモデル移行で変更したファイル:
- API: `apps/api/src/pci/config/settings.py`,
  `apps/api/src/pci/infrastructure/llm_comment_generator.py`,
  `apps/api/src/pci/presentation/dependencies.py`, `apps/api/.env.example`
- テスト: `apps/api/tests/unit/test_settings.py`,
  `apps/api/tests/unit/infrastructure/test_llm_comment_generator.py`
- 文書: `apps/api/README.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`,
  `docs/DECISIONS.md`, `docs/adr/0008-commentary-generation-strategy.md`,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

ゼロコスト既定モードで変更したファイル:
- API: `apps/api/src/pci/config/settings.py`, `apps/api/src/pci/presentation/dependencies.py`,
  `apps/api/.env.example`, `apps/api/README.md`
- テスト: `apps/api/tests/unit/test_settings.py`,
  `apps/api/tests/unit/presentation/test_dependencies.py`
- 文書: `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
  `docs/adr/0008-commentary-generation-strategy.md`, `tasks/current.md`, `tasks/backlog.md`,
  `docs/HANDOFF.md`

`7997931`（Phase2＋UI刷新）で変更したファイル:
- ingestion: `models.py`（ResultRecord+人気/賞金）, `parser/jv_spec.py`（SE予約offset Ninki/Honsyokin）,
  `parser/se_parser.py`（読取+妥当性ゲート）, `client/mykeibadb_client.py`（列→合成書込）,
  `ingest_api.py`（payload）, `tests/test_mykeibadb_client.py`（round-trip +2）
- API: `presentation/routers/ingest.py`（ResultItem）, `application/dto.py`（ResultInput）,
  `application/race_use_cases.py`（RecordRaceResult 反映）, `domain/racing/race_entry.py`（フィールド）,
  `infrastructure/database/models.py`（ORM列）, `infrastructure/repositories/race_repository.py`（read/write）,
  `alembic/versions/003_add_entry_popularity_prize.py`（新規migration）,
  `domain/pace/ability.py`（ability-v2 ブレンド）, `tests/unit/domain/pace/test_ability.py`（+4）
- 型/web: `packages/api-client/openapi.json`+`src/schema.d.ts`（再生成）,
  `apps/web/src/components/IntegratedRankingView.tsx`（印→タグ・順位主役に全面刷新）
- ドキュメント: `docs/SPEC.md`（§3.6 ability-v2化・§9-16更新）, `docs/DECISIONS.md`（2026-07-21（2））,
  `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`（§7.5 migration+再取込手順）,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

`8cda3bb`（統合順位予想 Phase1: ability-v1/integrated-v1・domain+app+schema+web+contract）で変更:
  `e286d94`（送信失敗可視化+RA突き合わせ）, `ccd6dc2`（診断ツール）, `af922a5`（DATA_KUBUN・空振り）。

（展開恩恵馬frame_noガード追加はコミット `e2f0b3c`、自動同期special-entries修正は `c49ce05`、
JV-Data仕様追従ガイド新規作成は `24731ed`、旧handoffファイル削除は `f2a8ea6`、
mypy誤情報訂正の変更ファイル一覧はコミット `9ed1ff7`、データ取り込み鮮度監視は `2b83d75`、
style-advantage-v1 は `3d3131e`、Codex実装分 `2b083ba`/`c679e09`/`4d9e5b5` の変更ファイル
一覧は各コミットまたは `docs/DECISIONS.md`/`docs/SPEC.md` の該当エントリ参照）

---

## 未確定仕様

- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかは未確定
  （`docs/SPEC.md §9`-3）。基準を定めた側（プロダクトオーナー）の確認が必要。
- ❓ PAI の正式定義・重み（pai-v1 は暫定、`docs/SPEC.md §9`-1）。
- ❓ 脚質判定ルールの最適化基準、展開コメントのLLM本採用可否、本番認証・課金仕様
  （いずれも `docs/SPEC.md §9` にリストあり、詳細はそちらを参照）。
- ❓ Geminiの正式運用品質基準・費用上限・モデル更新時の受入手順。任意実装とフォールバックは
  完成しているが、無料枠・料金・提供モデルはGoogle側で変更され得る。
- 🔎 formation-v1 の脚質70%・近走序盤位置30%と4ゾーン境界は実データ評価前の仮仕様
  （`tasks/current.md` の「暫定定数の検証と正式化」に追跡タスクあり）。
- 🔎 `STALE_AFTER_DAYS=4`（取り込み鮮度監視の暫定閾値）が実運用（週3回同期）に対して
  適切かは、しばらく運用してから検証する（`docs/SPEC.md §9`-13）。
- 🔎 RA/SE（`jv_spec.py`）の実測校正済みバイトオフセットが JV-Data仕様書の Ver.3.0.0 と
  Ver.4.9 のどちらの出力を元にしたものかは未確認（`docs/SPEC.md §9`-8、本セッションで発見）。
  UM/KS/CH（`master_parsers.py`）は既に Ver.4.9 相当への移行を確認済みだが、RA/SEは
  README.md/common.pyが「Ver.3.0準拠」表記のまま。再検証手順は
  `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` に明文化済み（実施はWindows実行機が必要）。
- ✅ 展開コメント自然文の枠順未確定表示は`comment-v2`で解決済み。
- 🔎 **`mykeibadb_client._build_se_record()`のDATA_KUBUN修正（2026-07-20）は実DB未検証**
  （`docs/SPEC.md §9`-15、`docs/DECISIONS.md` 2026-07-20）。コードリーディングのみに基づく
  仮説的な修正で、ユーザーの再同期結果で検証されるまでは「原因はこれで確定」と扱わないこと。

## 仮実装

- 🧪 `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 `FormationWeights`（脚質0.7・近走序盤位置0.3）。`formation-v1` として隔離済み。
- 🧪 `DistanceStyleWeights`（近走減衰・距離差・先行距離補正）。
  `running-style-v2-distance` として隔離済みで、隊列ゾーン一致率による再検証が必要。
- 🧪 `StyleAdvantageWeights`（勾配4.0/pt・逃げ追込増幅1.2・逃げ競合減点6.0/頭）。
  `style-advantage-v3`として隔離済み。7月小倉芝1200mの`reference`条件は馬場状態バックフィル後に見直す。
- 🧪 `STALE_AFTER_DAYS=4`（取り込み鮮度監視、`domain/ops/ingest_log.py`。本セッション追加）。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- **未確認（Gemini）**: 実APIキーを用いた疎通は未実施。単体テストではHTTP成功・失敗・
  モデル上書き・ルールフォールバックをモック検証済み。ローカルで疎通する場合は費用条件を
  公式料金表で確認してから`COMMENT_GENERATOR_MODE=gemini`と`GEMINI_API_KEY`を設定する。
- **解決済み**: 確定成績が2026-07-12以降反映されなかった件（上記「完了した作業」2.）。診断で
  解析は正常と判明、`batch.py`が`record_results`失敗をexit 0に握りつぶしていた欠陥を可視化。
  ユーザーが最新コードで再実行→全レース送信成功しアプリに反映。
- **未解決（ユーザー保留）**: 障害競走の成績が別途未反映。今回の一連とは切り分けて保留中。
- **残置（空振り・無害）**: `_build_se_record()`のDATA_KUBUN修正（`af922a5`）。真因ではなかったが
  単調・無害のため残置。
- **修正済み**: 展開恩恵馬カード等が枠順未確定の馬番を確定情報のように表示していた
  （`e2f0b3c`、上記「完了した作業」3.）。
- **修正済み**: 自動同期スクリプトが`--step special-entries`を一度も呼んでいなかった
  （`c49ce05`、上記「完了した作業」4.）。

---

## テスト状況（2026-07-21・統合順位予想 Phase 2完成後）

### OpenAI Codex による Phase 2完成後の全量確認

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `PYTHONPATH=src python -m pytest tests/unit tests/contract -q` | **440 passed** |
| ingestion-worker | `PYTHONPATH=src python -m pytest tests -q` | **191 passed** |
| API変更対象Ruff | `python -m ruff check <変更ファイル>` | **成功** |
| ingestion変更対象Ruff | `python -m ruff check <変更ファイル>` | **成功** |
| API import境界 | `lint-imports` | **2 kept, 0 broken** |
| API型 | `python -m mypy src --strict --python-version 3.12` | 既存`lgbm_forecaster.py:58` unused-ignore 1件のみ |
| api-client型 | `npm.cmd run typecheck --workspace=@pci/api-client` | **成功** |
| Web単体 / 型 / build | `npm.cmd run test` / `typecheck` / `build` | **65 passed** / **成功** / **成功** |
| OpenAPI | `PYTHONPATH=src python scripts/export_openapi.py` + api-client generate | **再生成済み** |

注意: WindowsのグローバルPythonには別チェックアウト`C:\Users\yuuta\PCI_app`がeditable installされている。
検証時は必ず現在の作業ツリーで`PYTHONPATH=src`を明示すること。実DBバックテストとJV-Link COM実地確認は未実行。

### OpenAI Codex によるマージ後再確認（2026-07-21）

`origin/claude/sweet-einstein-ilnaov` の16コミットを取り込むマージ中に、競合解消後の状態で以下を再実行した。
このCodex環境では `python`/`py`/`ruff`/`mypy`/`lint-imports` がプロジェクトvenvとして使える状態ではなく、
API/ingestion-worker の全量pytest・ruff・mypyは再実行できなかった。Claude Code 側の全量結果は下表に残す。

| 対象 | コマンド | 結果 |
|---|---|---|
| 競合マーカー確認 | `rg -n "<<<<<<<|=======|>>>>>>>"` | **該当なし** |
| API 構文確認 | `python.exe -m py_compile src\pci\application\backtest.py scripts\backtest_forecast.py tests\unit\application\test_backtest.py`（Codex bundled Python） | **成功** |
| api-client 型 | `npm.cmd run typecheck --workspace=@pci/api-client` | **成功** |
| Web 型 | `npm.cmd run typecheck`（apps/web） | **成功** |
| Web 単体 | `npm.cmd run test`（apps/web） | **65 passed** |
| Web build | `npm.cmd run build`（apps/web） | **成功** |

補足: Codexローカルの `144ebfd` は同目的のJSON保存を先に実装していたが、リモート `03bc005` の
`report_to_dict`/`--output` 実装が既に存在したため、競合ファイルはリモート版を採用した。

| 対象 | コマンド | 結果 |
|---|---|---|
| **API 単体+契約** | `.venv/bin/python -m pytest tests/unit/ tests/contract/ -q`（要 venv・下記注意事項） | **436 passed** |
| API Lint | `.venv/bin/ruff check src/ tests/ scripts/` | 既存 `scripts/seed_dev.py` 10件のみ（未編集ファイル・無関係。新規0） |
| API import境界 | `.venv/bin/lint-imports` | **2 kept, 0 broken** |
| API 型（全体） | `.venv/bin/python -m mypy src/ --strict` | 既存 `lgbm_forecaster.py:58` unused-ignore 1件のみ（当環境のlightgbm差異・無関係。新規0） |
| OpenAPI同期 | `test_committed_openapi_is_in_sync` | **成功**（`export_openapi.py`で再生成済み） |
| api-client 型 | `npm run typecheck`（packages/api-client） | **成功** |
| Web 単体 / 型 / build | `npm run test` / `typecheck` / `build`（apps/web） | **65 passed** / **成功** / **成功** |
| **ingestion-worker 単体** | `.venv/bin/python -m pytest tests/ -q`（要 3.12 venv） | **185 passed** |
| ingestion-worker Lint | `.venv/bin/ruff check src/ tests/` | 既存18件のみ（`windows_client.py`/`locate_corners.py`/`test_batch_e2e.py`等・未編集ファイル。新規0） |
| ingestion-worker 型 | `.venv/bin/python -m mypy src/ --strict` | 既存25件のみ（pymysqlスタブ欠如・`mykeibadb_client.py`のtuple-concatパターン・`batch.py`の`ingest_masters`。新規0） |

未実行: integration（Docker/testcontainers前提）。実DB依存の検証はこのクラウド環境から不可。

---

## 注意事項

- **新コンテナでは apps/api も依存未インストール。** 素の `python` に pytest/fastapi 等が無く、
  `pytest`/`mypy` は `uv tool` の隔離環境（プロジェクト依存なし）を指すことがある。
  **apps/api でも venv を作ること**: `cd apps/api && python -m venv .venv && .venv/bin/pip install -e ".[dev]"`、
  以降 `.venv/bin/python -m pytest` / `.venv/bin/python -m mypy src/ --strict` / `.venv/bin/ruff` /
  `.venv/bin/lint-imports` を使う（`.venv` は gitignore 済み）。ingestion-worker は 3.12 venv（別項）。
  **2026-07-12判明**: 「mypy全体でスタブ未導入エラー多数」は誤りで、venv経由なら実質0エラー
  （当環境で残る `lgbm_forecaster.py:58` unused-ignore 1件は lightgbm のバージョン差由来で無害）。
- このクラウド実行環境からは本番相当DB（mykeibadb蓄積データ）に**接続できない**。
  実データに依存する検証（バックテスト・実運用での鮮度判定・Webhook到達確認等）は
  ユーザーに手元（Windows機）で実行してもらい、出力を貼ってもらって分析する進め方になる。
- `backtest_forecast.py` の track別内訳表示は予測を2回実行するため、`--limit` を大きくすると
  実行時間が伸びる（上記「完了した作業」14.の既知のトレードオフ参照）。
- UI（Next.js）には PCI/RPCI/PAI の実数値を出さない方針（`docs/PROJECT_RULES.md §5`）。
  ただし CLI診断ツール（`backtest_forecast.py`等）は開発者向けであり、この方針の対象外
  （実数値をprintするのは意図的な挙動）。取り込み鮮度監視の失敗詳細（エラー要約）も、
  対象がPCI/RPCI等の指標ではなく運用ログのため同ルールの対象外（運用者本人向け情報）。
- `batch.py --mode mykeibadb` の `entries`/`results` と `special-entries` は**別のmykeibadbテーブル**
  （前者はRA/SE、後者はTOKUBETSU_TOROKUBA系）を読む独立ステップ。`--step all` は
  masters/entries/resultsのみで special-entries は含まれない。「取り込みが動いている」ことと
  「特別登録も含めて動いている」ことは別。今後この領域を触る際は両方を意識すること
  （2026-07-13、自動同期スクリプトの呼び出し漏れとして発見）。
- **`frame_no`（枠番）は`horse_no`（馬番）と別概念で、確定タイミングも異なる**。特別登録段階
  （枠順確定前）では`frame_no=0`かつ`horse_no`が`ingest_entries()`の暫定連番の場合がある。
  新しく馬単位の出力を追加する際は、`frame_no`（0=未確定/1〜8=確定）で判定してから`horse_no`を
  「確定馬番」として扱うこと。既存の判定基準は`formation.has_confirmed_draw()`
  （レース全体で1つの判定）と`lib/pace.ts`の`horseNumberLabel()`（表示ラベル）の2箇所
  （2026-07-13、`HorseFitOutput`の表示バグ修正で追加）。
- **`apps/ingestion-worker`はPython 3.12専用**（`pyproject.toml`の`requires-python`）。
  このクラウド環境の既定Pythonは3.11で、かつ最初はpytest等が一切インストールされていない
  （apps/apiと違い事前セットアップ済みの環境ではない）。テストを実行する際は
  `cd apps/ingestion-worker && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
  で環境を作り、`.venv/bin/python -m pytest tests/`を使うこと（2026-07-20判明）。
- **mykeibadbの列マッピング関連の不具合は「無いのではなく、値の意味が合わない」形で起きやすい**。
  過去に列名不一致で確定成績が全件消えた回帰
  （`test_iter_se_records_parses_results_from_wmykeibadb_columns`）があり、今回のDATA_KUBUN
  修正もその変種（列は存在するが値の意味づけが期待と異なる）。mykeibadb連携で「取り込みは
  成功するのにデータが空/古いまま」という報告を受けたら、まずこの種の暗黙の前提のズレを疑う
  こと（2026-07-20）。

---

## 次の担当者が最初に読むべきファイル（順番）

1. `docs/HANDOFF.md`（このファイル）— 現状把握
2. `docs/PROJECT_RULES.md` — Claude/Codex 共通の遵守ルール（最重要）
3. `CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex）— ツール固有の指示
4. `tasks/current.md` — 進行中タスク（現在は進行中なし。直近の完了は安全な手動再同期支援）
5. `docs/SPEC.md` — 確定/未確定仕様の区別（§3.6 に統合順位予想 ability-v3 を記載）
6. `docs/DECISIONS.md` — 直近の設計判断（2026-07-22: 安全な再同期コマンド提示、展開コメントのゼロコスト既定化、
   Gemini 3.5 Flash移行・環境変数化、comment-v2の馬番号表示、LightGBMモデルLF固定・現行AbilityWeights維持。
   2026-07-21（3）: grade優先のability-v3・確定馬体重の永続化・検証指標。
   2026-07-21: 統合順位予想 Phase1（2軸分類・現データのみ）、確定成績未反映の解決。
   2026-07-20（2）: 切り分け診断ツール導入。
   2026-07-13の2件: 展開恩恵馬frame_noガード追加・自動同期special-entries追加。
   2026-07-12の4件: ingest-status鮮度監視・style-advantage-v1・formation-v1・
   running-style-v2-distance）
7. 必要に応じて `docs/ARCHITECTURE.md`, `docs/adr/0005-rpci-forecast-strategy.md`

## 次の担当者が最初に実行すべきコマンド

```bash
# 1. 最新化・状態確認
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -10
git status   # クリーンであるはず

# 2. API 健全性確認（新コンテナは依存未インストール。venvを作り .venv/bin 経由で実行する）
cd apps/api
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -m "not integration" -q   # 464 passed
.venv/bin/ruff check src/ tests/
.venv/bin/lint-imports
.venv/bin/python -m mypy src/ --strict   # ローカルNumPy型定義とPython 3.11設定の不整合に注意

# 3. api-client 型 + Web 健全性確認（新コンテナは node_modules 未インストール）
cd ../../packages/api-client && npm install && npm run typecheck
cd ../../apps/web && npm install && npm run test && npm run typecheck && npm run build

# 4. ingestion-worker 健全性確認（Python 3.12専用。3.12でvenvを作る）
cd ../ingestion-worker
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q   # 185 passed
```

**統合順位予想 Phase2を実データで反映する場合**: ユーザーが Windows 機で
`alembic upgrade head`（migration 003）＋過去 results の再取込が必要（`MANUAL_SYNC_GUIDE.md §7.5`）。
これにより人気・本賞金・grade・確定馬体重が揃う。未実施でも、ability-v3は欠損成分を
自動で除外し、grade欠損時はrace_class推定へ縮退する。
