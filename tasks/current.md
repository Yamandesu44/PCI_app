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

- [ ] **P1 想定RPCI 受入基準の判定方針を決める（製品判断）**
  - 状態: ⬜未着手（ユーザー判断待ち）
  - 背景: 上記検証により MAE は構造的未達、ラベル一致率はダートのみ未達と判明。
    「このまま運用継続」か「追加投資（特徴量・学習データ拡張）」かの方針が必要。
  - 対象: `docs/SPEC.md §9`-2/3, `docs/adr/0005` の Consequences/緩和策
  - 依存: なし（いつでも着手可能。ユーザーへの確認が先）

- [ ] **P2 `backtest_forecast.py` の既定出力に track 別内訳を追加**
  - 状態: ⬜未着手
  - 背景: 混合集計だと PAI point-biserial が希釈されて見える落とし穴が判明（本セッション）。
  - 対象: `apps/api/scripts/backtest_forecast.py`, `apps/api/src/pci/application/backtest.py`
  - 完了条件: `--track-type` 未指定時に芝/ダート別の内訳も併記する、またはドキュメントで
    track別実行を必須化する注意書きを追加。

---

## 保留・ブロック中

- [ ] ⏸ **P2 統合テスト（testcontainers-postgres）の実行環境整備**
  - 状態: ⏸保留（Docker / DB 前提。CI or ローカルで要環境）
  - 対象: `apps/api/tests/integration/`
  - メモ: 現在は unit+contract のみ日常実行。infrastructure 層の実 DB 経路は integration 依存。
