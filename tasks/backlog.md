# tasks/backlog.md — 未着手タスク・改善候補・技術的負債

> 現時点で確認できる未着手事項を整理する。**確定タスク**（やると決まっている）と
> **改善案/検討**（やるかどうか未確定）を区別する。着手したら `tasks/current.md` へ移す。

最終更新: 2026-07-21

---

## A. 確定タスク（方針は決定済み・未着手）

- [x] ~~P1 想定RPCI の精度検証~~ → **検証完了**（2026-07-11、`docs/SPEC.md §8`・ADR-0005 §5.4）。
- [x] ~~P1 未達なら要因追加の判断~~ → **方針決定済み**（2026-07-11、`docs/DECISIONS.md`）。
  当面は追加投資せず現行モデルを継続、`forecast_accuracy` 蓄積で継続監視。見直し条件あり。
- [x] ~~P1 `forecast_accuracy` のフロント表示~~ → 完了（コミット `e65f919`）。
- [x] ~~P2 backtest_forecast.py の PAI希釈対策（track別内訳表示）~~ → 完了（2026-07-11、
  `group_races_by_track` + `_print_track_breakdown`）。
- [x] ~~P2 バックテスト結果の可視化/保存~~ → 完了（2026-07-12、`report_to_dict` + `--output`）。
  JSON保存のみ実装。DBテーブル化は見送り（的中率推移ダッシュボードが要る段階で再検討）。
- [x] ~~P2 Windows ワーカー運用の監視強化（失敗の可視化）~~ → 完了（2026-07-12、
  `GET /api/v1/ingest-status` + `IngestStatusBanner`）。**残課題**: `NOTIFY_WEBHOOK_URL`
  によるWebhook通知が実際に届くかは、Windows実行機での実地確認が必要（このクラウド環境から不可）。
  再実行導線（画面からの手動再実行トリガー）は未着手（要判断: ボタン一発で本当に安全に
  再実行できるか、多重実行防止をどうするか）。
- [ ] **P2 取り込み監視を「実行成否」から「データ完全性」へ拡張**（2026-07-20 確定成績未反映事件の
  再発防止提案・未着手）。現状の`evaluate_freshness`（`domain/ops/ingest_log.py`）は batch実行の
  ok/経過日数のみを見ており、「過去日なのに確定成績が未反映のまま残ったレース」は検知できない。
  当時ユーザーが目視していた「成績未取込レース」一覧（`page.tsx`のレスキュー表示）を、レース側から
  能動的にスキャンして自動アラート化できれば、同種の問題が今後1週間以上気づかれないことを防げる。
  ユーザーは2026-07-21時点で②統合順位予想を優先したため未着手。再提案候補（最初に推奨した項目）。

## B. 改善候補（やるか未確定・要判断）

- [x] ~~P1 展開＋絶対能力の統合順位予想（Phase1）~~ → **2026-07-21 実装済み**（ability-v1 ×
  integrated-v1、`docs/SPEC.md §3.6`・`docs/DECISIONS.md` 2026-07-21）。現データのみ・2軸分類。
- [x] ~~P1 統合順位予想 Phase2: 人気・本賞金の永続化（ability-v2）~~ → **2026-07-21 実装済み**
  （`docs/DECISIONS.md` 2026-07-21（2）・`docs/SPEC.md §3.6`）。人気(TANSHO_NINKIJUN)・本賞金
  (KAKUTOKU_HONSHOKIN)を永続化し ability-v2 でブレンド。運用は `MANUAL_SYNC_GUIDE §7.5`。
- [x] ~~P1 統合順位予想 Phase2 残: 馬体重・grade の永続化~~ → **2026-07-21 実装済み**。
  確定馬体重は既存 `race_entries.weight` へresults再取込時にも更新。gradeはRA GradeCD[615]を公式コード
  から変換し、ability-v3のクラス補正で直接利用。馬体重は根拠不足のため能力加点には使わない。
- [ ] **P1 AbilityWeightsの実DB比較検証**。バックテストに1位馬勝率・1位馬好走率・TOP3好走捕捉率を
  追加済み。現行重みと候補重みを同一期間で比較し、改善が再現した場合のみ正式化する。
- [ ] **P2 実JV-Dataの人気/賞金予約オフセット検証**（jvlink実COM用）。現状はmykeibadb合成専用。
- [ ] 🧪 暫定定数の検証と正式化: `_NEIGHBOR_BLEED_RATIO`(affinity)・上がり3F 妥当範囲(se_parser)・
  `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`FormationWeights`(formation-v1)・
  `DistanceStyleWeights`(running-style-v2-distance)・`StyleAdvantageWeights`(style-advantage-v1)・
  `STALE_AFTER_DAYS`(ingest_log鮮度監視)。実データ・実運用での検証後に確定（独断で確定しない）。
- [ ] 脚質判定ルールの最適化（design/07 C9・データ蓄積後）。
- [ ] 展開コメントの LLM（Gemini）本採用可否と品質基準（ADR-0008）。数値はドメイン確定・表現のみ LLM。
- [ ] PAI 正式定義の確定（design/07 C10・実運用検証後）。
- [ ] ダート「ハイ」(17.2%)/芝「平均(49–51)」(14.3%)再現率の構造的課題への対応
  （2026-07-11実測、ADR-0005 §5.4・§5.3）。閾値調整では解決不可と結論済み（rule-v5試行）。
  特徴量追加・学習データ拡張が候補。**現時点では未着手が方針**（`docs/DECISIONS.md` 2026-07-11）。
  見直し条件（`forecast_accuracy`蓄積増加・ダートの外れの偏り）に該当したら着手を検討。

## C. 技術的負債・環境

- [x] ~~`mypy src/ --strict` を全体で通すための SQLAlchemy/Pydantic/FastAPI スタブ導入 or 設定~~
  → **2026-07-12 判明・対応済み**: スタブ不足ではなく、素の `mypy` コマンドが `uv tool` 等の
  隔離環境（プロジェクト依存関係が入っていない）を指していた誤検知だった。
  `python -m mypy src/ --strict` で実行すると **56ファイル全体で0エラー**（キャッシュ削除後も再現）。
  `CLAUDE.md`/`AGENTS.md`/`docs/PROJECT_RULES.md`/`docs/ARCHITECTURE.md`/`apps/api/README.md`の
  誤記載を訂正し、DoDも「domain・applicationのみ」から「全体で0エラー」へ引き上げ。
- [x] ~~旧 `docs/handoff-claude-code-2026-06-25.md` の記載ファイル名が現構成と不一致~~
  → **2026-07-13 削除**: 内容を精査した結果、全項目が (a) 現構成と食い違う誤情報
  （`domain/services.py`・`infrastructure/repositories.py` は現存しない旧パス、
  「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
  （ローカル起動手順→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
  同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）であり、
  「吸収すべき未収録の情報」が残っていなかったため削除（`docs/ARCHITECTURE.md`への吸収は不要）。
  Git履歴には残るため復元可能。
- [ ] 統合テスト（testcontainers-postgres）の日常実行環境（CI/ローカル Docker）整備。
- [x] ~~JV-Data バイトオフセットの JV-Link 新バージョン追従手順の明文化（`jv_spec.py`）~~
  → **2026-07-13 手順書作成**: `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` を新規作成。
  `dump_records.py`→`verify_layout.py`→`locate_haron.py`/`locate_corners.py`→`jv_spec.py`更新の
  流れと安全策を明文化。副次的に、UM/KS/CH（`master_parsers.py`）はVer.3.0.0→Ver.4.9移行を
  実データで確認済みだが、RA/SE（`jv_spec.py`）は README.md/common.py が「Ver.3.0準拠」表記の
  まま未確認という具体的なギャップを発見（`docs/SPEC.md §9`-8）。**手順の明文化は完了、
  実際の再検証実施はWindows実行機（JV-Link必須）が必要なため引き続き未着手。**

## D. 将来スコープ（MVP 外・design/07 参照）

- [ ] 当日リアルタイム速報更新（C6/C7）
- [ ] 地方競馬対応（C5・中央で価値実証後）
- [ ] 認証・課金・マルチテナント（C11・SaaS 化フェーズ）
- [ ] バックフィル 10年への拡張（C8・運用安定後）
- [ ] 正式公開時の JRA-VAN 規約適合性確認（C2・法務）
