# tasks/current.md — 進行中タスク

> 進行中・直近着手のタスクをチェックボックスで管理する。着手/完了のたびに更新する。
> 状態: ⬜未着手 / 🔄進行中 / ✅完了 / ⏸保留。優先度: P0(必須) / P1(高) / P2(中) / P3(低)。
> 単なる改善案・未着手の候補は `tasks/backlog.md` に置く。

最終更新: 2026-07-11 / 担当: Claude Code / ブランチ `claude/sweet-einstein-ilnaov`

---

## 進行中

（現在なし。直近完了分は下記「最近完了したタスク」を参照）

---

## 最近完了したタスク

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

## 次に着手する候補（今スプリントの当面）

（現在なし。`tasks/backlog.md` の B/C/D 節から次を選ぶか、ユーザー指示待ち）

---

## 保留・ブロック中

- [ ] ⏸ **P2 統合テスト（testcontainers-postgres）の実行環境整備**
  - 状態: ⏸保留（Docker / DB 前提。CI or ローカルで要環境）
  - 対象: `apps/api/tests/integration/`
  - メモ: 現在は unit+contract のみ日常実行。infrastructure 層の実 DB 経路は integration 依存。
