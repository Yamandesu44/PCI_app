# tasks/current.md — 進行中タスク

> 進行中・直近着手のタスクをチェックボックスで管理する。着手/完了のたびに更新する。
> 状態: ⬜未着手 / 🔄進行中 / ✅完了 / ⏸保留。優先度: P0(必須) / P1(高) / P2(中) / P3(低)。
> 単なる改善案・未着手の候補は `tasks/backlog.md` に置く。

最終更新: 2026-07-22（安全な手動再同期コマンド導線） / 担当: OpenAI Codex / ブランチ `claude/sweet-einstein-ilnaov`

詳しい状態は `docs/HANDOFF.md` を参照（このファイルはタスクの一覧管理に専念する）。

---

## 進行中

（現在、進行中の未完了タスクはなし。直近の大タスクは下記「最近完了したタスク」参照。）

---

## 最近完了したタスク

- [x] ✅ **P2 成績未取込警告から安全な手動再同期コマンドを提示**
  - DBで最古の未取込日を集計し、標準10日以上の`recommended_sync_days_back`をAPIへ追加。
  - Web警告バナーに`run_mykeibadb_full_sync.ps1 -DaysBack N`のコピーUIを追加。正常時は非表示。
  - APIからWindowsプロセスを直接起動せず、認証・多重実行・配置差のリスクを回避。
  - OpenAPIとapi-client型を再生成。
  - 検証: API非統合464 passed、Repository統合1 passed、Web67 passed、Ruff、変更対象mypy、
    api-client/Web typecheck、Web build成功。

- [x] ✅ **P1 展開コメント生成をゼロコスト既定モードへ変更**
  - `COMMENT_GENERATOR_MODE=rule`を既定とし、APIキーが環境に残っていても外部APIを呼ばない。
  - Geminiは`COMMENT_GENERATOR_MODE=gemini`と`GEMINI_API_KEY`の両方を明示した場合だけ有効化。
  - Gemini指定時のキー欠損・初期化失敗は`comment-v2`へフォールバックする。
  - 公開APIスキーマ・コメント計算・Web表示は変更なし。
  - 検証: API非統合463 passed、関連29 passed、ruff成功、変更対象2ファイルのmypy strict成功。
    全体mypyは既知のNumPy型定義とPython 3.11設定の不整合で解析前に停止。import-linterは未導入。

- [x] ✅ **P2 Gemini既定モデルを3.5 Flashへ移行し、環境変数化**
  - 提供終了した`gemini-2.0-flash`から`gemini-3.5-flash`へ既定モデルを更新。
  - `GEMINI_MODEL`でモデルを上書き可能にし、DIから`GeminiCommentGenerator`へ渡す。
  - Gemini出力を`comment-gemini-v3`へ更新し、`reasons`には実際に使用したモデル名を記録。
  - APIキー未設定・呼出失敗時の`comment-v2`フォールバックは維持。実APIは呼び出していない。
  - 検証: API非統合457 passed、関連23 passed、ruff成功、変更対象3ファイルのmypy strict成功。

- [x] ✅ **P2 枠順未確定時の展開コメント馬番号表示を修正（comment-v2）**
  - `formation-v1`と同じ枠順確定判定をscenario・ルールコメント・Geminiプロンプトへ結線。
  - 共通の`horse_number_label.py`で、未確定時は「登録順 N（馬番未確定）」、確定後だけ
    「N番」と表示する。API公開スキーマは変更していない。
  - 出力変更を追跡するため、ルール版を`comment-v2`、Gemini版を`comment-gemini-v2`へ更新。
  - 検証: API非統合454 passed、関連74 passed、ruff成功、変更対象5ファイルのmypy strict成功。
    import-linterはローカル環境に未導入。全体mypyは既知のNumPy型定義不整合で解析前に停止。

- [x] ✅ **P1 LightGBMモデルのWindows改行破損修正・AbilityWeights実DB採用判断**
  - `.gitattributes`で`apps/api/models/*.txt`をLF固定。LightGBMの`tree_sizes`がCRLF変換で
    壊れ、実モデルを読めなくなる問題を修正した。既存clone向けにローダーでもLFへ自己修復する。
  - モデル読込失敗時のフォールバックを警告ログへ記録し、追跡中の芝・ダートモデルを実際に
    ロード・予測する回帰テストを追加。
  - 実DBを2025年後半212レース、2026年前半97レースに分けて4候補を比較。
    全3指標が両期間で改善する候補はなく、現行重み（0.55/0.30/0.15）を維持する。
  - 検証: API非統合449 passed、LightGBM関連31 passed、ruff、実DBバックテストCLI成功。
    mypyはローカルNumPy型定義とPython 3.11設定の不整合で対象コード解析前に停止。

- [x] ✅ **P2 取り込み監視をデータ完全性へ拡張**（本セッション・OpenAI Codex）
  - 前日以前のレースが `status=entries` のまま残っている件数と代表20件を、
    `GET /api/v1/ingest-status` で返すようにした。
  - Webトップの `IngestStatusBanner` に成績未取込警告と対象レースへのリンクを追加。
    取り込みログが無い環境でも、未取込レースがあれば警告する。
  - API非統合テスト447件、関連SQL統合テスト1件、Webテスト66件、ruff、Web型チェック・本番ビルド成功。
    mypyはローカルNumPy型定義とPython 3.11設定の不整合で依存型解析前に停止（新規コード原因ではない）。

- [x] ✅ **P1 AbilityWeightsの同一期間比較CLI**（本セッション・OpenAI Codex）
  - `backtest_forecast.py --compare-ability-weights`を追加し、現行・近走のみ・近走重視・
    市場支持重視の4候補を同じ対象レースで比較。
  - 1位馬勝率・1位馬好走率・TOP3好走捕捉率と現行差を表示し、`--output`のJSONにも保存。
  - 候補は検証専用で、`DEFAULT_WEIGHTS`は自動更新しない。実DB実行と採用判断は上記タスクで完了。
  - 検証: API unit+contract 444 passed（関連は40 passed）、変更対象Ruff、
    mypy strict 58ファイル成功、CLI `--help`成功。

- [x] ✅ **P1 統合順位予想 Phase 2 完成（grade・確定馬体重・検証指標）**（本セッション・OpenAI Codex）
  - grade: RA `GradeCD[615]` を公式コードから名称へ変換し、mykeibadb→API→`races.grade`へ保存。
    ability-v3はgradeをクラス補正へ優先利用し、欠損時だけrace_class推定へ縮退。
  - 馬体重: SE `BaTaijyu[324:327]` をresults payloadにも追加し、results単独再取込でも既存
    `race_entries.weight`を確定馬体重で更新。体格と能力を直結させる根拠がないため能力加点は見送り。
  - 検証: バックテストへ統合順位の1位馬勝率・1位馬好走率・TOP3好走捕捉率とJSON出力を追加。
  - テスト: API unit+contract 440 passed、ingestion 191 passed、Web 65 passed、API/ingestion変更対象Ruff、
    lint-imports、api-client/web typecheck、Web build成功。mypy strictは既存lgbm unused-ignore 1件のみ。

- [x] ✅ **P0 Claude Code リモート更新の統合と引き継ぎ資料更新**（本セッション・OpenAI Codex）
  - 状況: Codex が `tasks/current.md` の最優先候補（バックテスト結果のJSON保存）に着手し
    `144ebfd feat(backtest): export reports as json` を作成したが、push前にリモートが16コミット進んでいた。
  - 判断: リモート側 `03bc005 feat(backtest): persist backtest reports to JSON via --output` が同じ目的を
    既に実装済みで、後続コミット（統合順位予想Phase2等）も含まれていたため、マージ競合では
    `apps/api/src/pci/application/backtest.py`・`apps/api/scripts/backtest_forecast.py`・
    `apps/api/tests/unit/application/test_backtest.py`・各ドキュメントをリモート版で採用。
    重複実装で新しいClaude Code作業を上書きしないことを優先した。
  - 検証: 競合マーカーなし、API backtest関連の `py_compile` 成功、api-client typecheck成功、
    Web test 65 passed・typecheck/build成功。API/ingestion-workerの全量pytest/ruff/mypyは
    このCodex環境でPython dev toolingが未構築のため再実行不可（Claude Code側の全量結果は
    `docs/HANDOFF.md` に保持）。

- [x] ✅ **P1 統合順位予想: 印→タグUI・順位明確化 ＋ Phase2（人気・本賞金→ability-v2）**（本セッション）
  - UI（ユーザーFB）: `IntegratedRankingView` を刷新。◎○▲△の印を廃止し、総合順位（1位…）を主役に、
    分類は言葉タグ（本命/対抗/穴（妙味）/人気でも注意/能力上位・中位/展開が向く・向きにくい）で表示。
    プレゼン層のみ（ドメイン/スキーマ不変）。
  - Phase2 データ: 人気(TANSHO_NINKIJUN)・獲得本賞金(KAKUTOKU_HONSHOKIN)を永続化。
    ingestion（models/se_parser/jv_spec 予約offset/mykeibadb_client/ingest_api）→ API（ingest schema・
    ResultInput・RaceEntry・use case・ORM・repository・migration 003）→ ability-v2。
  - ability-v2: form0.55＋本賞金(対数正規化)0.30＋人気0.15 を新しさ加重ブレンド。データ無し成分は
    除外し再正規化 → 旧データは form のみ＝v1相当へ安全に縮退。本賞金がクラス係数 best-effort の限界を緩和。
  - **運用（ユーザー作業）**: `alembic upgrade head`（migration 003）＋過去 results の再取込が必要
    （`MANUAL_SYNC_GUIDE §7.5`）。やらなくても壊れない（縮退）。
  - 検証: API 436 passed（+ability-v2 4件・parser round-trip等）、ingestion 185 passed（+2）、
    Web 65 passed・typecheck・build clean、ruff/lint-imports/mypy clean（既存lgbm/tuple-concat debtのみ・新規0）。
  - 後続で馬体重・gradeを追加済み（上記）。残るのは実JV-Dataの人気/賞金オフセット検証。

- [x] ✅ **P1 統合順位予想（能力×展開）Phase1 実装**（本セッション・ユーザー選択のB節要望を再開）
  - 判断: データ範囲=現データのみ / 統合=2軸分類（本命/対抗/穴/危険）（ユーザー選択・`docs/DECISIONS.md` 2026-07-21）。
  - domain: `pace/ability.py`（ability-v1: 出走頭数正規化着順×クラス係数の新しさ加重平均）、
    `pace/integrated_ranking.py`（integrated-v1: 能力相対順位×展開適性の2軸分類・決定的表示順）。
    いずれも純粋・reasons付き・model_version付き。🧪仮係数は `AbilityWeights`（`docs/SPEC.md §9`-16）。
  - 結線: `forecast_use_cases`（近走+過去レースからability構築→統合）, `dto.py`, `schemas.py`,
    OpenAPI再生成（`openapi.json`+`schema.d.ts`）, `api-client/src/index.ts`（型追加）。
  - web: `IntegratedRankingView.tsx`（新規・◎○▲△と能力上位/中位・展開向く/向きにくいを言葉表示、
    実数値は非表示）を `RaceForecastDashboard` の隊列予想の前に配置。
  - 当時の既知の限界: `grade`未永続化のためクラス係数は`race_class`文字列のbest-effortだった。
    本セッションのability-v3でgrade・人気・本賞金・確定馬体重の永続化まで完了済み。
  - 検証: API 432 passed（+新規domain16・contract1）、Web 65 passed、api/web typecheck・build・
    ruff・lint-imports・mypy --strict すべてclean（既存のlgbm 1件は当環境固有・無関係）。

- [x] ✅ **P0 確定成績未反映を解決**（本セッション・§9-15）
  - 診断で「解析は正常（453件解析可・DATA_KUBUN='7'）」→原因は解析より下流と特定。`batch.py`が
    `record_results`失敗をexit 0に握りつぶしていた欠陥を修正し、送信成功/失敗の件数ログを常設。
    ユーザーが最新コードでresultsステップを再実行→全レース送信成功しアプリに反映（解決）。
  - 残: 障害競走の成績が別途未反映（ユーザー保留）。`DaysBack`既定 7→10 済み。

- [x] ✅ **P0 確定成績未反映の切り分け診断ツール＋件数ログ＋日付窓修正**（本セッション2巡目）
  - 契機: DATA_KUBUN修正（`af922a5`）投入後もユーザー環境で確定成績が反映されず、同期ログは
    全ステップexit 0（件数ではない）。「exit 0で0件」だけでは原因層を特定できないと判明。
  - 対応:
    - `batch.py`: `ingest_results`に「SE何行読込／確定成績何行解析／何レース記録」の件数INFOログ、
      「SE行>0だが確定成績0行」なら診断コマンドを促すWARNINGを追加。`ingest_entries`にも件数ログ。
    - `ingestion/diagnose_results.py`(新規): 実DBのSE行を読み、着順/タイム/上り3F列の有無・
      DATA_KUBUN分布・parse_se_result成功数・SEテーブルの実列名一覧を出力。判定セクションで
      (A)mykeibadb未取得 / (B)列名不一致 / (C)バイト配置バグ を切り分ける。個人・馬名系列は既定で伏せる。
    - `run_mykeibadb_full_sync.ps1`: `DaysBack`既定 7→10（月曜実行時に前々週土曜が窓外へ漏れる
      問題を緩和。7/12の欠落はこれで説明可能）。長期バックフィル用に`-DaysBack 21`例を明記。
  - 対象: `apps/ingestion-worker/src/ingestion/batch.py`,
    `apps/ingestion-worker/src/ingestion/diagnose_results.py`(新規),
    `apps/ingestion-worker/tests/test_diagnose_results.py`(新規3件),
    `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
  - 検証: pytest 182 passed（+3）、ruff clean（新規ファイル）、mypy --strict clean（diagnose_results/
    batch.pyとも新規エラーなし。batch.pyの既存4件はingest_masters内・未編集で対象外）。
  - **未解決**: 診断ツールの実行はユーザー環境（Windows+MySQL）でのみ可能。出力を受け取り次第
    (A)/(B)/(C)を確定して次の手を打つ。上記「進行中」に残置。

- [x] 🧪 **P0（未検証・空振り） 確定成績1週間以上未反映の原因調査とDATA_KUBUN修正**（本セッション）
  - 調査: entries/special-entriesは動いているのに確定成績だけが1週間以上反映されないという
    ユーザー報告を受け、`mykeibadb_client._build_se_record()`を確認。着順・タイム・上り3Fは
    無条件にバイト列へ書き込まれる一方、DataKubun（確定判定に使う値）は`DATA_KUBUN`列が
    存在すればその値をそのまま採用し、存在しない場合のみ着順等の有無から推測していた。
    実環境の`DATA_KUBUN`列がJV-Data本来の確定コードを正しく反映していない場合、着順等が
    揃っていても`parse_se_result`が`None`を返し続ける、という一貫した説明がつく。
  - 対応: 着順・タイム・上り3Fが全て揃っていれば`DATA_KUBUN`列の値に関わらず'7'（確定）とする
    よう変更（単調な修正で、揃っていない行を誤って確定扱いにする副作用はない）。
    `apps/ingestion-worker/tests/test_mykeibadb_client.py`に回帰テストを追加。
  - 検証: `apps/ingestion-worker`は3.12専用のためこの環境にpython3.12でvenvを作成し
    `pip install -e ".[dev]"`後に実行。pytest 179 passed（+1）、ruff/mypy（該当ファイルは
    差分前後で0/25エラーのまま=新規エラーなし）clean。
  - **結果（空振り）**: ユーザーが再pull＆再同期したが確定成績は反映されず、この仮説は外れ
    （または原因の一部でしかない）と判明。修正自体は単調で無害なため残置。真因は別（診断ツールで
    切り分け中。上記の2巡目タスク参照）。

---

- [x] ✅ **P0 展開恩恵馬カードが枠順未確定の馬番を確定情報のように表示するバグを修正**（本セッション）
  - ユーザー報告: 枠順確定前のレースなのに展開予想画面の「展開恩恵馬TOP5」等に馬番が出ている。
  - 原因: `formation-v1`（隊列予想）は`frame_no`（枠番）で確定/未確定を判定し未確定時は
    `formation: null`にする設計だったが、同じ画面のPAI系出力`HorseFitOutput`にはそもそも
    `frame_no`が無く、この判定が一切されていなかった。特別登録段階の`horse_no`は
    `ingest_entries()`がUMABAN=0時に割り当てる暫定連番で、公式馬番ではない。
  - 対応: `HorseFitOutput`/`HorseFitSchema`に`frame_no`を追加（`forecast_use_cases.py`で
    `RaceEntry.frame_no`から供給）。web側`lib/pace.ts`に`horseNumberLabel()`を新設し、
    `frame_no>0`なら「馬番 N」、`frame_no=0`なら「登録順 N（馬番未確定）」を表示。
    `RaceForecastDashboard.tsx`・`HorseFitTable.tsx`・`app/page.tsx`の計5箇所を統一。
    PAIスコア自体は枠順確定前でも意味があるため、カードごと非表示にはせずラベルのみ是正。
  - 対象: `application/dto.py`, `application/forecast_use_cases.py`, `presentation/schemas.py`,
    `openapi.json`+`schema.d.ts`(再生成), `apps/web/src/lib/pace.ts`(+テスト2件),
    `apps/web/src/components/RaceForecastDashboard.tsx`, `apps/web/src/components/HorseFitTable.tsx`,
    `apps/web/src/app/page.tsx`, `tests/unit/application/test_forecast_use_cases.py`(+1件),
    `tests/contract/test_races_api.py`(HORSE_KEYS更新)
  - 検証: API 415 passed（+1）、Web 65 passed（+2）、ruff/mypy --strict/lint-imports/
    typecheck/build すべてclean。
  - 後続対応: `scenario.py`を含む自然文コメントの同種問題は2026-07-22の`comment-v2`で解決済み。

- [x] ✅ **P0 自動同期が来週の特別登録を一度も取り込んでいなかったバグを修正**（本セッション）
  - ユーザー報告「月曜なのに土日の結果・来週の特別登録馬が未反映」を受けて
    `run_mykeibadb_full_sync.ps1`（Task Scheduler「PCI_Sync_Mykeibadb」金/土10:00・日18:00が実行）の
    中身を確認。`batch.py --step entries`/`--step results` のみを呼んでおり、`--step special-entries`
    （mykeibadbの`TOKUBETSU_TOROKUBA`系テーブルを読む独立ステップ）を一度も呼んでいなかったと判明。
    `setup_task_scheduler.ps1`自身のdocstringには「日曜18:00は来週の重賞特別登録取り込みも兼ねる」と
    明記されており、実装漏れ（2026-07-11のTask Scheduler自動化切替時に追加し忘れたと推測）と判断。
  - 対応: `run_mykeibadb_full_sync.ps1`に3番目の呼び出し（`-Step special-entries`、同じ過去7日〜
    未来14日の日付窓）を追加。`sync_mykeibadb.bat`・`MANUAL_SYNC_GUIDE.md`（手順・注意書き・
    6.8節トラブルシューティング新設）・`docs/SPEC.md §6`・`docs/DECISIONS.md`を更新。
  - コード上の修正のみでは今週分の取りこぼしは遡って埋まらないため、ユーザーには
    `--step special-entries`の手動実行コマンドを別途案内。
  - 未解決: 「土日の確定成績が反映されていない」側は自動実行の対象内（`--step results`）のはずで、
    「取りこぼし」ではなく「実行自体の失敗/未発火」の可能性が高いが、このクラウド環境からは
    Task Scheduler実行履歴・ログ・MySQL80状態を確認できないため、ユーザー自身の診断が必要
    （`MANUAL_SYNC_GUIDE.md §6.8`に診断手順を用意）。上記「進行中」に残置。

- [x] ✅ **P3 JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化（技術的負債）**（本セッション）
  - 背景: `jv_spec.py`（RA/SE）のオフセットは実データ校正済みだが、JV-Linkが仕様バージョンを
    上げた場合の再検証手順が文書化されていなかった。
  - 調査で判明: UM/KS/CH（`master_parsers.py`）は既に Ver.3.0.0→Ver.4.9 の実データ差分
    （日付フィールド群24byte追加による名前位置シフト）を確認・反映済みという実例が存在した。
    一方RA/SE側は README.md/common.py が「Ver.3.0準拠」と書いたままで、実際にどのバージョンの
    出力を元に校正したかは未確認と判明（独断で確定せず `docs/SPEC.md §9`-8 に記録）。
  - 対応: `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` を新規作成。UM/KS/CHの実例を
    土台に、`dump_records.py`→`verify_layout.py`（アンカー検証→フィールド目視確認）→
    `locate_haron.py`/`locate_corners.py`（新オフセット特定）→`jv_spec.py`更新→テスト更新→
    記録、の手順と安全策（1レースだけでCONFIRMED昇格しない等）を明文化。
    `README.md`・`docs/SPEC.md`（§6, §9-8）から相互参照を追加。
  - コード変更なし（ドキュメントのみ）。実際の再検証はWindows実行機（JV-Link必須）が必要なため、
    ガイドの実施自体は引き続き未着手（`docs/SPEC.md §9`-8に残置）。

- [x] ✅ **P3 旧handoffファイルの整理（技術的負債）**（本セッション）
  - `docs/handoff-claude-code-2026-06-25.md` の内容を精査。全項目が (a) 現構成と食い違う
    誤情報（`domain/services.py`・`infrastructure/repositories.py`は現存しない旧パス、
    「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
    （ローカル起動→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
    同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）と判明。
    「吸収すべき未収録の情報」が残っていなかったため削除（Git履歴には残るため復元可能）。
  - 対応: ファイル削除、`tasks/backlog.md` 更新。他ドキュメントからの参照なし（削除前に確認済み）。

- [x] ✅ **P3 `mypy --strict` 全体化（技術的負債）**（本セッション、ドキュメント訂正のみ）
  - `tasks/backlog.md` C節に着手したところ、既存の「infrastructure/presentationはスタブ未導入で
    多数エラー・環境要因」という長年の記載が**誤りだったと判明**。
    `python -m mypy src/ --strict` を実行（`.mypy_cache`削除後も再現）すると
    **56ファイル全体で0エラー**。原因は素の`mypy`コマンドが`uv tool`等の隔離環境
    （プロジェクト依存関係が入っていない）を指していたこと（前セッションで発見した
    `pytest`の問題と同根）。fastapi/sqlalchemy/pydanticはいずれも`py.typed`同梱で型情報あり。
  - 対応: `CLAUDE.md`, `AGENTS.md`, `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`,
    `apps/api/README.md`, `tasks/backlog.md` の誤記載をすべて訂正。Definition of Doneも
    「domain・applicationのみ0エラー」から「全体で0エラー」へ引き上げ（実態を反映）。
  - コード変更なし。次回以降は `python -m mypy src/ --strict` を標準コマンドとして使うこと。

- [x] ✅ **P1 データ取り込みの鮮度監視（推奨1・「監視・鮮度表示」）**（コミット `2b83d75`）
  - 目的: `ingest_log` は書き込み専用で、自動同期が静かに失敗し続けても気づく手段が無かった。
  - 対応: 新規 `domain/ops/ingest_log.py`（`IngestLogRepository` Protocol +
    純粋関数 `evaluate_freshness()`）。判定は「直近試行の失敗有無」「直近成功からの経過日数
    （暫定閾値 `STALE_AFTER_DAYS=4`）」のみで、Task Schedulerの具体的cronはハードコードしない。
    `GET /api/v1/ingest-status`（公開GET、`/internal/ingest/*`の認証とは別）を新設し、
    web トップに `IngestStatusBanner` を追加（正常時は控えめ、鮮度低下・失敗時のみ目立つ表示、
    失敗一覧は開閉式）。ログが1件も無い環境（開発/fixture等）は「異常」ではなく「監視対象外」
    として扱い誤警告を防ぐ。
  - 対象: `domain/ops/ingest_log.py`(新規), `infrastructure/repositories/ingest_log_repository.py`(新規),
    `application/dto.py`, `application/ingest_status_use_cases.py`(新規), `presentation/schemas.py`,
    `presentation/routers/status.py`(新規), `presentation/dependencies.py`, `presentation/app.py`,
    `packages/api-client`(型+クライアントメソッド追加), `apps/web/src/lib/ingestStatus.ts`(新規),
    `apps/web/src/components/IngestStatusBanner.tsx`(新規), `apps/web/src/app/page.tsx`
  - 検証: API 414 passed（+18: domain 10・application 5・contract 3）、Web 63 passed（+6）、
    ruff/mypy --strict/lint-imports/typecheck/build すべてclean。
  - 未実施（ユーザー環境でのみ確認可能）: `NOTIFY_WEBHOOK_URL` によるWebhook通知が実際に届くかの
    実地確認。このクラウド環境からは検証不可。

- [x] ✅ **P1 脚質別有利度の差が出ない問題を修正（style-advantage-v1）**（コミット `3d3131e`）
  - ユーザー指摘: 展開分析の有利度が 71/76/91/96 のように高止まりし、機能していると言い難い。
  - 原因: web が「その脚質の最大PAI」を有利度として流用（脚質自体の有利さではない）。
  - 対応: domain に `style_advantage.py` を新設し、想定RPCIの中立点（classify_pace と同じ閾値中点:
    芝50/ダート43）からの乖離を 50=互角の対称スコアへ写像。逃げ競合減点あり。reasons/model_version 付き。
    DTO→schema→OpenAPI→api-client→web（`styleAdvantageScores` + 有利/互角/不利の言葉ラベル）まで結線。
  - 対象: `domain/pace/style_advantage.py`(新規), `application/dto.py`, `forecast_use_cases.py`,
    `presentation/schemas.py`, `tests/`(domain 12件+app 1件+contract 1件), `openapi.json`+`schema.d.ts`(再生成),
    `packages/api-client/src/index.ts`, `apps/web/src/lib/pace.ts`(+テスト2件),
    `apps/web/src/components/RaceForecastDashboard.tsx`
  - 検証: API 396 passed（+14）、Web 57 passed（+2）、ruff/mypy --strict/lint-imports/typecheck/build clean。
  - 関連: ユーザー要望②（展開＋絶対能力の統合順位予想）は `tasks/backlog.md` B節に P1 で記録
    （能力指数の定義が必要なため着手時に仕様合意から）。

- [x] ✅ **P2 バックテスト結果の可視化/保存**（コミット `03bc005`）
  - 対象: `apps/api/src/pci/application/backtest.py`（`report_to_dict`等の変換関数を追加）,
    `apps/api/scripts/backtest_forecast.py`（`--output <path>` オプション追加）,
    `apps/api/tests/unit/application/test_backtest.py`（`TestReportToDict` 2件追加）
  - 結果: `--output` 指定時、混合集計＋（`--track-type`未指定なら）track別内訳をJSONに保存。
    既存の `print` 出力は変更なし。DBテーブル化は見送り（推移ダッシュボードが要る段階で再検討、
    `tasks/backlog.md` A節に記録）。
  - 検証: `python -m pytest tests/unit/ tests/contract/ -q` 382 passed（+2）、ruff/mypy/lint-imports
    clean。`_write_output`の実ファイル書き込み・JSON往復読み込みを手動スモークテストで確認
    （スクリプト層はプロジェクト方針上ユニットテスト対象外のため）。

- [x] ✅ **P1 隊列予想の「自在」過多を距離対応の脚質予測で改善**（コミット `2b083ba`）
  - 原因調査: 直近20レース266頭で自在139頭のうち、混在履歴99頭・履歴なし40頭。
  - 明確な従来脚質は維持し、混在型だけを対象距離・過去走距離・近走順で再判定。
  - 先行・差し同数時は、先行歴が今回より短距離中心なら先行、長距離中心なら差しを優先。
  - 実DB: 自在139頭（52.3%）から40頭（15.0%）へ減少。履歴なしは参考表示を維持。
  - 検証: API unit+contract 380 passed、Web 55 passed、mypy/ruff/import-linter/typecheck/build成功。

- [x] ✅ **P1 枠順確定後の隊列予想機能**（コミット `c679e09`）
  - 特別登録の `frame_no=0` を除外し、全馬に実枠番がある場合だけ `formation-v1` を生成。
  - 脚質と近走序盤位置から、先頭・好位・中団・後方の4ゾーンへ配置。各馬に根拠と信頼度ラベルを付与。
  - OpenAPI型を更新し、展開予想画面にJRA枠色を使ったレスポンシブ隊列ビューを追加。
  - 実DB: entries 278件中、枠順確定112件で生成、未確定166件で非生成を確認。
  - 検証: API unit+contract 374 passed、Web 55 passed、mypy/ruff/import-linter/typecheck/build成功。

- [x] ✅ **P1 レース分析画面のモダンUI刷新**（コミット `4d9e5b5`）
  - 共通ヘッダーとデザイントークンを追加し、レース一覧・展開予想・確定後回顧を同じUIへ統一。
  - 一覧は開催日カレンダーをデスクトップのサイドバーへ移し、レースカードの状態・導線を明確化。
  - 予想・回顧はダークヒーロー、要約カード、解説、的中表示を情報優先度に沿って再構成。
  - 回顧画面の表面からPCIという専門用語を外し、数値を増やさずペース傾向として表示。
  - 検証: Web 55 tests / typecheck / production build がすべて成功。実データの一覧・予想・回顧URLがHTTP 200。

- [x] ✅ **P1 想定RPCI 受入基準の判定方針を決める（製品判断）**（`docs/DECISIONS.md` 2026-07-11）
  - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
  - 理由: MAEの未達幅は2回の独立計測で一貫した構造差。UIは実数値非表示のため、製品価値に直結する
    ラベル一致率(33%ランダムを上回る)とPAIリフト(track別1.18〜1.32x)は実効性ありと判断。
  - 見直し条件: `forecast_accuracy` 蓄積増加、またはダートの外れに偏りが見えた場合に再検討。
  - 注記: 受入基準の文言自体（blended/track別のどちらで判定するか）は基準を定めた側の確認が必要な
    別問題として `docs/SPEC.md §9`-3 に残置（この決定の範囲外）。

- [x] ✅ **P2 `backtest_forecast.py` の既定出力に track 別内訳を追加**
  - 対象: `apps/api/src/pci/application/backtest.py`(`group_races_by_track`追加),
    `apps/api/scripts/backtest_forecast.py`(`_print_track_breakdown`追加),
    `apps/api/tests/unit/application/test_backtest.py`(テスト2件追加)
  - 結果: `--track-type` 未指定時、混合集計に加え芝/ダート別内訳も自動表示。再予測はせず、
    既存の `ForecastBacktester.run()` を track 別サブセットで再実行するのみ（application層は
    グルーピングのみ純粋関数化しテスト、DB配線はスクリプト層のまま）。
  - 検証: `python -m pytest tests/unit/ tests/contract/ -q` 364 passed（+2）、ruff/mypy/lint-imports clean。

- [x] ✅ **P1 想定RPCI 精度の検証（受入基準の達成度確認）**（コード変更なし、ドキュメント更新のみ）
  - 対象: `docs/SPEC.md §8/§9`, `docs/adr/0005-rpci-forecast-strategy.md §5.4`
  - 実行: ユーザーが本番相当DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200`
    を実行（混合／芝のみ／ダートのみ）。結果をこちらで分析・記録。
  - 結果概要:
    - MAE≤1.5 は **未達（構造的）**。混合7.848 / 芝8.861 / ダート8.332 — 15,440レースの過去
      バックテストと整合する安定した値で、単発の外れ値ではない。
    - 展開ラベル一致率≥60% は **芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達**。
      受入基準文言が track 区別を明記していないため、判定基準（blended/track別）は未確定事項化。
    - **新知見:** 混合サンプルで PAI point-biserial を見ると +0.009（無相関）に見えるが、
      track別に分けると +0.084(芝)/+0.032(ダート) と過去記録どおりの正相関に戻る
      （母集団混在による希釈）。今後 PAI 検証は必ず `--track-type` を使うこと。
  - 未解決: 上記2件を `tasks/backlog.md` に追記（受入基準の判定方針決定、backtest ツールの
    track別内訳表示）。

- [x] ✅ **P1 AI 引き継ぎ基盤の整備**（コミット `004aead`）
  - 対象: `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
    `docs/HANDOFF.md`, `AGENTS.md`, `tasks/current.md`, `tasks/backlog.md`, `CLAUDE.md`(追記)

- [x] ✅ **P1 `forecast_accuracy` の UI 表示**（コミット `e65f919`）
  - 対象: `packages/api-client/src/index.ts`(型追加) + `schema.d.ts`(再生成),
    `apps/web/src/lib/pace.ts`(`forecastAccuracyMeta`), `apps/web/src/lib/pace.test.ts`,
    `apps/web/src/components/ForecastAccuracyBadge.tsx`(新規),
    `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`, `apps/web/src/app/globals.css`
  - 結果: pace-analysis 画面に「想定が的中/外れ」を**言葉・色**で表示（実数値は出さない）。
    予測未保存レースではバッジ非表示。vitest 3件追加（web計55件 green）。
  - 副次対応: `schema.d.ts` 再生成で、前回セッション（ingest_log 追加時）に反映漏れだった
    `IngestLogBody`/`IngestLogResponse`/`/internal/ingest/log` の型ドリフトも解消。

---

## 次に着手する候補（今スプリントの当面・優先順位順）

（進行中タスクはなし。以下は `tasks/backlog.md` から優先度順に抜粋した候補。
**着手前にユーザーへどれを選ぶか確認すること**（`docs/PROJECT_RULES.md` に沿い独断で選定しない）。）

- [ ] **P2 Windows ワーカー運用の監視強化**（`tasks/backlog.md` A節）
  - 状態: ⬜未着手
  - 背景: `ingest_log`（migration 002）は導入済みだが、失敗の可視化・再実行導線・
    `NOTIFY_WEBHOOK_URL` 通知の定着が未完了。
  - 完了条件: 直近の取り込み失敗が一覧できる（API or CLI）、失敗時にWebhook通知が実際に届くことを
    手元で確認済み。
  - ブロック要因: Webhook通知の動作確認にはユーザーの実行環境（Windows機）が必要。

- [ ] **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・上がり3F妥当範囲・`RuleWeights`・`PaiWeights`・
  `FormationWeights`・`DistanceStyleWeights`・`StyleAdvantageWeights`・`AbilityWeights`）
  - 状態: ⬜未着手
  - 背景: `docs/SPEC.md §9` に記載の仮仕様。実データ検証後に確定する方針（独断で確定しない）。
    `FormationWeights`（脚質70%/近走序盤位置30%・4ゾーン境界）と`DistanceStyleWeights`
    （距離スケール・新しさ減衰・先行距離補正）は2026-07-12にCodexが追加した仮係数
    （`docs/SPEC.md §9`-10, `docs/DECISIONS.md` 2026-07-12参照）。`AbilityWeights`
    （近走内容0.55/本賞金0.30/人気0.15のブレンド比・新しさ減衰・本賞金対数レンジ等）は
    2026-07-21にability-v2として追加（`docs/SPEC.md §9`-16）。
  - 完了条件: 対象定数ごとに実データでの妥当性検証結果を記録し、確定 or 調整の判断を
    `docs/DECISIONS.md` に残す。formation-v1については隊列ゾーン一致率（実際の後方カメラ等の
    確定データがあれば）での再検証が望ましいが、現状データで可能な範囲でよい。`AbilityWeights`は
    migration 003 適用＋過去成績再取込（`MANUAL_SYNC_GUIDE §7.5`）後でないと人気/本賞金データが
    無く検証できない点に注意。
  - ブロック要因: 実DBアクセスが必要（このクラウド環境からは接続不可。想定RPCI検証と同様、
    ユーザーに手元でスクリプト実行→結果を貼ってもらう進め方になる見込み）。着手前にどの定数を
    対象にするかユーザーに確認。

- [ ] **P3 技術的負債の解消（残件）**（`tasks/backlog.md` C節）
  - 状態: mypy strict全体化・旧handoffファイル整理・JV-Dataオフセット追従手順の明文化は完了
    （上記「最近完了したタスク」参照）。**残るは統合テスト環境整備のみ**。
  - 完了条件: `tasks/backlog.md` C節を参照。優先度は相対的に低い。
  - ブロック要因: Docker/testcontainers-postgresが必要（このクラウド環境では利用不可）。

---

## 保留・ブロック中

- [ ] ⏸ **ダート特徴量追加・学習データ拡張の検討**（`docs/DECISIONS.md` 2026-07-11参照）
  - 状態: ⏸保留（製品判断済み: 現時点では追加投資しない）
  - 見直し条件: `forecast_accuracy` の蓄積データが増える（track毎に100件超など）、
    または実運用でダートの外れ方に偏り（例: 常にハイ側へ外す）が見えた場合に着手を再検討。

- [ ] ⏸ **P2 統合テスト（testcontainers-postgres）の実行環境整備**
  - 状態: ⏸保留（Docker / DB 前提。CI or ローカルで要環境）
  - 対象: `apps/api/tests/integration/`
  - メモ: 現在は unit+contract のみ日常実行。infrastructure 層の実 DB 経路は integration 依存。
