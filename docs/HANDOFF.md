# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-20（更新9回目・確定成績1週間以上未反映の原因調査とDATA_KUBUN修正・未検証） |
| 作業担当AI | Claude Code |
| 直前の担当AI | OpenAI Codex（`4d9e5b5`〜`81ddb9d`の3実装+引き継ぎ文書を実施。検証済み・不整合なし） |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `e2f0b3c` fix(forecast): don't show unconfirmed horse numbers as if official |
| 作業ツリー | 本更新時点でmykeibadb_client.pyのDATA_KUBUN修正+関連ドキュメント更新がコミット前（下記「変更対象ファイル」参照） |

---

## 現在の作業目的

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
列の扱いに仮説的な原因を特定し修正（本セッション、下記「完了した作業」1.）。
**この修正は実DBで検証できておらず、ユーザーによる再同期後の確認が必要**。

---

## 完了した作業（直近セッション）

1. **確定成績1週間以上未反映の原因調査とDATA_KUBUN修正**（本セッション・未コミット・**未検証**）
   - ユーザー報告: 2026-07-12以降（7/12・7/18・7/19の全開催日）確定成績が一切反映されない一方、
     7/25・26の特別登録は正常に反映されている。「取り込み自体は動いているが確定成績の検出だけが
     機能していない」という状態で、しかも先に修正した`--step special-entries`の反映を確認する
     ための再同期を実施済みにも関わらず改善しなかった（単発の実行失敗ではなく再現性あり）。
   - 調査: `mykeibadb_client._build_se_record()`を確認。wmykeibadbが「列分解済みテーブル」で
     出力する環境（一般的なケース）では、着順・タイム・上り3Fの値は無条件にSEレコードのバイト
     位置へ書き込まれる一方、DataKubunバイト（`se_parser.parse_se_result`が'4'/'7'でのみ確定
     扱いする判定材料）は、`DATA_KUBUN`列が存在すればその値をそのまま採用し、存在しない場合
     のみ着順等の有無から'7'/'1'を推測していた。実環境の`DATA_KUBUN`列がJV-Data本来の確定
     コードを正しく反映していない場合、着順等のデータ自体は揃っているのに`parse_se_result`が
     毎回`None`を返し続ける、という一貫した説明がつく。同種の「列名/値の不一致で確定成績が
     全件消える」不具合は`test_iter_se_records_parses_results_from_wmykeibadb_columns`の
     コメントに過去の回帰として記録されており、今回はその変種と考えられる。
   - 対応: 着順・タイム・上り3Fが全て揃っている場合は`DATA_KUBUN`列の値に関わらず'7'（確定）
     とするよう変更（揃っていない行を誤って確定扱いにする副作用がない単調な修正）。
     `apps/ingestion-worker/tests/test_mykeibadb_client.py`に回帰テストを追加。
   - 検証: `apps/ingestion-worker`はPython 3.12専用（pyproject.toml）だが、このクラウド環境の
     既定Pythonは3.11のため、`python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
     でテスト環境を用意（同梱のsystem-wide環境には元々pytest等が入っていなかった）。
     pytest 179 passed（+1）、ruff（変更ファイルのみ0エラー）、mypy --strict（変更前後で
     25エラーのまま=新規エラーなしを確認）。
   - **重要な限界（未検証）**: このクラウド環境からは実DB・実mykeibadbスキーマにアクセス
     できず、静的なコードリーディングのみに基づく仮説的な修正。ユーザーが本修正を反映して
     再同期し、確定成績が実際に反映されるようになるかで検証が必要（`docs/DECISIONS.md`
     2026-07-20参照）。直らない場合はこの仮説が誤りで、mykeibadb.exe/wmykeibadb側
     （このリポジトリのコード外の要因）を疑う必要がある。

2. **展開恩恵馬カードが枠順未確定の馬番を確定情報のように表示するバグを修正**（`e2f0b3c`）
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
   - **未対応（既知の残課題）**: `scenario.py`の自然文コメント内「馬番 N」表記は同種の問題が
     残る（`docs/SPEC.md §9`-14）。`HorsePaceProfile`/`PaiResult`にframe_no相当が無く、対応には
     domain層拡張が必要なため今回は対象外。露出箇所は「判定根拠データ」アコーディオン内のみで、
     ユーザー報告の箇所（常時表示カード）とは異なる。
   - 検証: API 415 passed（+1）、Web 65 passed（+2）、ruff/mypy --strict/lint-imports/
     typecheck/build すべてclean。

3. **自動同期が来週の特別登録を一度も取り込んでいなかったバグを修正**（`c49ce05`）
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

4. **JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化**（`24731ed`）
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

5. **旧handoffファイルの整理**（`f2a8ea6`）
   - `docs/handoff-claude-code-2026-06-25.md` を精査。全項目が (a) 現構成と食い違う誤情報
     （`domain/services.py`・`infrastructure/repositories.py`は現存しない旧パス、
     「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
     （ローカル起動→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
     同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）と判明。
     「吸収すべき未収録の情報」が残っていなかったため削除（Git履歴には残り復元可能）。
   - 他ドキュメントからの参照は `tasks/backlog.md` のみだったことを確認済み（削除後に更新）。

6. **mypy --strict 全体エラーは誤情報だったと判明・訂正**（`9ed1ff7`、コード変更なし）
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

7. **データ取り込みの鮮度監視**（`2b83d75`）
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
     届くかの実地確認。画面からの手動再実行導線も未着手（`tasks/backlog.md` A節に残課題として記録）。

8. **脚質別有利度の修正（style-advantage-v1）**（`3d3131e`）
   - 原因: web が「その脚質の最大PAI」を有利度に流用しており、スコアが60〜96に高止まり。
   - 対応: `domain/pace/style_advantage.py` 新設。想定RPCIの中立点（classify_pace と同じ
     rule-v4 閾値の中点: 芝50/ダート43）からの乖離を 50=互角の対称スコア（0〜100）へ写像。
     逃げ・追込は増幅1.2、逃げ候補2頭以上で逃げのみ競合減点。reasons/model_version 付き。
   - `StyleAdvantageWeights` は🧪仮係数（`docs/SPEC.md §3.4/§9`-11、`docs/DECISIONS.md` 2026-07-12）。

9. **バックテスト結果のJSON保存**（`03bc005`）
   - `report_to_dict()` + `--output <path>`。混合＋track別内訳をJSON保存。print出力は不変。

10. **Codex引き継ぎ内容の検証**（`af66e8f`、ドキュメントのみ）
   - ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従（無傷）。
   - Codexの実装3件をコードレベルで検証し、テストを独立再実行。重大な不整合なし。

11. **混在型脚質の距離対応予測**（`2b083ba`、Codex実装・検証済み）
   - 直近20レース266頭を調査し、旧自在139頭のうち99頭が60%未満の混在、40頭が履歴なしと確認。
   - 明確な `running-style-v1` 判定は維持し、混在型だけ `running-style-v2-distance` で再判定。
   - 過去5走の4角位置、対象距離との距離差、近走順を使用。先行・差し同数時の距離規則を追加。
   - 予想日以後の成績を参照しないよう、履歴取得に開催日前カットオフを明示。
   - 同じ266頭で自在を139頭（52.3%）から40頭（15.0%）へ削減。履歴なしは参考のまま維持。
   - API 380件、Web 55件、ruff/mypy/import-linter/typecheck/buildがすべて成功。

12. **枠順確定後の隊列予想**（`c679e09`、Codex実装・検証済み）
   - `domain/pace/formation.py` に枠順確定判定と formation-v1 を追加。
   - 全馬の枠番が1〜8、馬番が正かつ一意の場合のみ予想し、特別登録（frame_no=0）は `null`。
   - 脚質70%・近走の1角（欠損時4角）位置30%で先頭/好位/中団/後方へ配置。
   - 各馬に日本語の根拠と「高・標準・参考」の信頼度ラベルを付与。
   - OpenAPI/API Clientを再生成し、WebにJRA枠色の `FormationView` を追加。
   - 契約テストの予測器をルールベースへ固定し、WindowsのLightGBMネイティブabortを回避。
   - 実DBで entries 278件、枠順確定112件は生成、未確定166件は非生成を確認。

13. **レース分析UIの刷新**（`4d9e5b5`、Codex実装・検証済み）
   - `AppHeader` を追加し、全画面でブランドとレース一覧への導線を固定。
   - レース一覧を最大幅拡張し、統計、開催日カレンダー、日付・競馬場別レースを2カラム化。
   - 展開予想と確定後回顧へ共通のダークヒーローとエメラルドのアクセントを導入。
   - 予想サマリー、初心者向け解説、展開恩恵馬、評価を下げたい馬の視覚階層を整理。
   - 回顧画面は「PCI判定」を「ペース傾向」へ翻訳し、内部実数値を新たに露出していない。
   - モバイルでは1カラム、デスクトップでは一覧のカレンダーをstickyサイドバーとして表示。

以下は以前の完了作業:

14. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
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
15. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
16. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
17. **`forecast_accuracy` の UI 表示**（`e65f919`）、**AI 引き継ぎ基盤整備**（`004aead`）、
    **予測フィードバックループ**（`9712fd2`）ほか、それ以前の完了作業は
    `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

- **確定成績1週間以上未反映の件、修正は投入したが実DBでの検証待ち**（ユーザー報告、本セッション）。
  `mykeibadb_client._build_se_record()`のDATA_KUBUN列扱いを修正したが、静的なコードリーディング
  のみに基づく仮説であり、このクラウド環境からは実DBで確認できない。ユーザーが再同期して
  確定成績が反映されるようになるか確認依頼中（回答待ち）。直らない場合はmykeibadb.exe/
  wmykeibadb側（コード外の要因）を疑う必要がある。
- ユーザー要望②「**展開＋絶対能力の統合順位予想**」は保留中（ユーザー判断・`tasks/backlog.md` B節）。
  能力指数の算出方法自体の模索が必要なため。再開時はまず指標案をユーザーへ提示して合意を取ること。
- **Windows実行機での実地確認が必要な残課題**（このクラウド環境からは検証不可）:
  `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に届くか。`special-entries`呼び出しを追加した
  自動同期スクリプト自体がWindows実行機で問題なく動くかも未確認。
- 画面からの手動再実行導線は未着手（`tasks/backlog.md` A節。多重実行防止等の設計が必要）。
- **JV-Data仕様追従の実施自体は未着手**（`apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md`で
  手順は明文化したが、実データ取得にはWindows実行機＋JV-Linkが必要でこのクラウド環境からは不可。
  RA/SEが実際にVer.3.0.0/Ver.4.9のどちらの出力を元に校正されたかも未確認のまま、`docs/SPEC.md §9`-8）。
- 展開コメント自然文（`scenario.py`）内の「馬番 N」表記が枠順未確定時を区別できない件
  （`docs/SPEC.md §9`-14）。domain層拡張が必要な既知の残課題として記録のみ、対応は未着手。
- それ以外はなし。本セッションの変更はこれからコミットする。

## 現在止まっている箇所

**確定成績未反映修正の実DB検証**（上記「未完了の作業」参照）。ユーザーが再同期を実施し、
結果（直った/直っていない、直っていなければログ）を共有してくれるまで、このクラウド環境からは
これ以上の診断・対応が進められない。

---

## 次に実施すべき作業（候補・優先順位順）

**最優先**: 上記「現在止まっている箇所」— ユーザーが再同期の結果を共有してくれ次第、
直っていればクローズ、直っていなければログを元に次の仮説を検証する。それ以外にユーザーからの
新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する
（A節が方針決定済み、B節は着手可否に判断が必要、C節は技術的負債）。**どれを選ぶかは
ユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針に沿う）。

1. **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・`RuleWeights`・`PaiWeights`・
   `FormationWeights`・`DistanceStyleWeights`・`StyleAdvantageWeights`・`STALE_AFTER_DAYS` 等）
   - 実データ・実運用での検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行/
     しばらく運用→結果を分析」の進め方になる可能性が高い。着手前にどの定数を対象にするか確認する。
2. **P3 技術的負債（残件: 統合テスト環境整備のみ）**
   - `mypy --strict` 全体化・旧handoffファイル整理・JV-Dataオフセット追従手順明文化は本セッションで
     完了（`tasks/backlog.md` C節）。統合テスト環境整備はDocker前提（このクラウド環境からは不可）。
     着手前にユーザーに確認。

**保留・確認待ちの項目**:
- **P1 展開＋絶対能力の統合順位予想**（`tasks/backlog.md` B節・ユーザー要望2026-07-12）
  — ユーザー判断で保留中。再開の合図があれば、能力指数の定義案（例: 直近N走の着順/クラス/
  持ち時計/上がり順位の合成）を提示するところから始める。
- 画面からの手動再実行導線（`tasks/backlog.md` A節）— 要判断（安全性・多重実行防止の設計）。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張（2026-07-11決定） — `forecast_accuracy` 蓄積が増える、
  またはダートの外れに偏りが見えた場合に再検討。

---

## 変更対象ファイル（本セッション・コミット前）

- 更新（ingestion-worker・コード、**未検証**）:
  `apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`（`_build_se_record()`の
  DATA_KUBUN判定ロジック修正）,
  `apps/ingestion-worker/tests/test_mykeibadb_client.py`（回帰テスト+1件）
- 更新（ドキュメント）: `docs/SPEC.md`（§6にバグ修正・§9-15に検証待ちを追記）,
  `docs/DECISIONS.md`（2026-07-20エントリ追加）, `tasks/current.md`（進行中・完了タスク更新）,
  `docs/HANDOFF.md`（本ファイル）

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
- 🔎 formation-v1 の脚質70%・近走序盤位置30%と4ゾーン境界は実データ評価前の仮仕様
  （`tasks/current.md` の「暫定定数の検証と正式化」に追跡タスクあり）。
- 🔎 `STALE_AFTER_DAYS=4`（取り込み鮮度監視の暫定閾値）が実運用（週3回同期）に対して
  適切かは、しばらく運用してから検証する（`docs/SPEC.md §9`-13）。
- 🔎 RA/SE（`jv_spec.py`）の実測校正済みバイトオフセットが JV-Data仕様書の Ver.3.0.0 と
  Ver.4.9 のどちらの出力を元にしたものかは未確認（`docs/SPEC.md §9`-8、本セッションで発見）。
  UM/KS/CH（`master_parsers.py`）は既に Ver.4.9 相当への移行を確認済みだが、RA/SEは
  README.md/common.pyが「Ver.3.0準拠」表記のまま。再検証手順は
  `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` に明文化済み（実施はWindows実行機が必要）。
- 🔎 展開コメント自然文（`scenario.py`）の「馬番 N」表記は`HorseFitOutput`と異なり枠順未確定時の
  区別が未対応（`docs/SPEC.md §9`-14、本セッションで発見・対応は未着手）。domain層
  （`HorsePaceProfile`/`PaiResult`）にframe_no相当が無く、対応にはdomain層拡張が必要。
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
  `style-advantage-v1` として隔離済み（`docs/SPEC.md §9`-11）。
- 🧪 `STALE_AFTER_DAYS=4`（取り込み鮮度監視、`domain/ops/ingest_log.py`。本セッション追加）。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- **修正済み（未検証）**: `mykeibadb_client._build_se_record()`がDATA_KUBUN列の値を無条件に
  信用しており、この値が確定コードを正しく反映しない環境では確定成績が検出されなかった
  （本セッション、上記「完了した作業」1.、`docs/DECISIONS.md` 2026-07-20参照）。
  **実DBでの検証待ち**。
- **修正済み**: 展開恩恵馬カード等が枠順未確定の馬番を確定情報のように表示していた
  （`e2f0b3c`、上記「完了した作業」2.）。
- **修正済み**: 自動同期スクリプト（`run_mykeibadb_full_sync.ps1`）が`--step special-entries`を
  一度も呼んでおらず、来週の特別登録馬が自動では反映されなかった（`c49ce05`、上記
  「完了した作業」3.）。
- **未特定・修正対応済みで検証待ち**: 確定成績が2026-07-12以降1週間以上反映されない件
  （原因の仮説と修正は上記「完了した作業」1.、実際に直るかはユーザーの再同期結果待ち）。

---

## テスト状況（2026-07-20・DATA_KUBUN修正後）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `python -m pytest tests/unit/ tests/contract/ -q` | **415 passed**（+1） |
| API Lint | `ruff check src/ tests/` | **成功**（`scripts/seed_dev.py`に無関係な既存10件あり・未着手） |
| API 型（全体） | `python -m mypy src/ --strict` | **成功（56 files、0エラー）** |
| import境界 | `lint-imports` | **2 kept, 0 broken**（domain/ops も含め依存方向OK） |
| OpenAPI同期 | `test_committed_openapi_is_in_sync` | **成功**（`export_openapi.py`で再生成済み） |
| api-client 型 | `cd packages/api-client && npm run typecheck` | **成功** |
| Web 単体 | `cd apps/web && npm run test` | **65 passed**（+2） |
| Web 型 | `npm run typecheck` | **成功** |
| Web build | `npm run build` | **成功**（3ページ + not-found） |
| **ingestion-worker 単体（今回）** | `.venv/bin/python -m pytest tests/ -q`（要 Python 3.12 venv、下記注意事項参照） | **179 passed**（+1） |
| ingestion-worker Lint（変更ファイルのみ） | `ruff check src/ingestion/client/mykeibadb_client.py tests/test_mykeibadb_client.py` | **成功** |
| ingestion-worker 型（全体・既存25件は対象外） | `mypy src/ --strict` | 変更前後で**25エラーのまま**（新規エラーなし。既存debtは対象外） |

未実行: integration（Docker/testcontainers前提）。実DB依存の検証（実運用での鮮度判定の
振る舞い、Webhook通知の到達確認、`special-entries`自動呼び出しが実際にWindows実行機で
動くかの実地確認、**そして今回のDATA_KUBUN修正が実際に確定成績を反映させるかの検証**）は
このクラウド環境から不可。ユーザーの実環境での確認を推奨。

---

## 注意事項

- **`pytest`/`mypy` 単体コマンドはこの実行環境では `uv tool` の隔離環境（プロジェクトの依存関係が
  入っていない）を指す場合がある。** `python -m pytest` / `python -m mypy` を使うこと。
  `which pytest` や `which mypy` が `/root/.local/bin/...` を指す場合はこの問題に当たっている
  可能性が高い。**2026-07-12判明**: 従来「`mypy src/ --strict`を全体にかけるとinfrastructure/
  presentationでスタブ未導入エラーが多数出る（環境要因）」と広く記載されていたが、これは誤り
  だった。`python -m mypy src/ --strict` なら全体で0エラー。詳細は各docsの訂正箇所を参照。
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
4. `tasks/current.md` — 進行中タスク（確定成績未反映修正の実DB検証待ちが進行中。
   次候補は本ファイル「次に実施すべき作業」参照）
5. `docs/SPEC.md` — 確定/未確定仕様の区別
6. `docs/DECISIONS.md` — 直近の設計判断（2026-07-20: DATA_KUBUN修正（未検証）。
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

# 2. API 健全性確認（pytest/mypy は python -m 経由で使うこと。素のコマンドは
#    隔離環境を指しfastapi等が「見つからない」誤検知になり得る）
cd apps/api
python -m pytest tests/unit/ tests/contract/ -q
ruff check src/ tests/ scripts/
lint-imports
python -m mypy src/ --strict   # 全体で0エラーが基準（domain/applicationだけではない）

# 3. Web 健全性確認
cd ../web
npm run test
npm run typecheck

# 4. ingestion-worker 健全性確認（Python 3.12専用。このクラウド環境は3.11が既定のため
#    3.12でvenvを作る必要がある。apps/apiと違い事前セットアップ済みではない）
cd ../ingestion-worker
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q
```
