# tasks/current.md — 進行中タスク

> 進行中・直近着手のタスクをチェックボックスで管理する。着手/完了のたびに更新する。
> 状態: ⬜未着手 / 🔄進行中 / ✅完了 / ⏸保留。優先度: P0(必須) / P1(高) / P2(中) / P3(低)。
> 単なる改善案・未着手の候補は `tasks/backlog.md` に置く。

最終更新: 2026-07-12 / 担当: Claude Code（Codexからの引き継ぎ内容を検証済み） / ブランチ `claude/sweet-einstein-ilnaov`

引き継ぎ検証: 2026-07-12 Claude Code。ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従
（コンフリクトなし・Codexの変更は無傷）。Codexの実装3件（running-style-v2-distance/formation-v1/UI刷新）を
コードレベルで検証し、API側の全テスト（`python -m pytest` 380 passed, ruff/mypy --strict/lint-imports すべて
成功）・Web側（vitest 55 passed, typecheck/build成功）・OpenAPI/schema.d.ts再生成ドリフトなしを自ら再実行して確認。
重大な不整合なし（詳細はチャット履歴の検証報告を参照）。

---

## 進行中

（現在なし。直近完了分は下記「最近完了したタスク」を参照）

---

## 最近完了したタスク

- [x] ✅ **P2 バックテスト結果の可視化/保存**（本セッション、コミット予定）
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
  `FormationWeights`・`DistanceStyleWeights`）
  - 状態: ⬜未着手
  - 背景: `docs/SPEC.md §9` に記載の仮仕様。実データ検証後に確定する方針（独断で確定しない）。
    `FormationWeights`（脚質70%/近走序盤位置30%・4ゾーン境界）と`DistanceStyleWeights`
    （距離スケール・新しさ減衰・先行距離補正）は2026-07-12にCodexが追加した仮係数
    （`docs/SPEC.md §9`-10, `docs/DECISIONS.md` 2026-07-12参照）。
  - 完了条件: 対象定数ごとに実データでの妥当性検証結果を記録し、確定 or 調整の判断を
    `docs/DECISIONS.md` に残す。formation-v1については隊列ゾーン一致率（実際の後方カメラ等の
    確定データがあれば）での再検証が望ましいが、現状データで可能な範囲でよい。
  - ブロック要因: 実DBアクセスが必要（このクラウド環境からは接続不可。想定RPCI検証と同様、
    ユーザーに手元でスクリプト実行→結果を貼ってもらう進め方になる見込み）。着手前にどの定数を
    対象にするかユーザーに確認。

- [ ] **P3 技術的負債の解消**（`tasks/backlog.md` C節: mypy strict全体化・統合テスト環境整備・
  旧handoffファイル整理・JV-Dataオフセット追従手順の明文化）
  - 状態: ⬜未着手
  - 完了条件: 各項目は `tasks/backlog.md` C節を参照。優先度は相対的に低い。
  - ブロック要因: 統合テスト環境整備はDocker/testcontainers-postgresが必要。

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
