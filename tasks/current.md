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

- [ ] **P1 想定RPCI 精度の検証（受入基準の達成度確認）**
  - 状態: ⬜未着手
  - 対象: `apps/api/scripts/backtest_forecast.py`, `apps/api/src/pci/application/backtest.py`
  - 完了条件: 蓄積データで MAE / 展開ラベル一致率を集計し、design/07 の基準（MAE≤1.5・一致率≥60%）に
    対する現状を `docs/SPEC.md §8` へ反映。未達要因を記録。
  - 関連テスト: `tests/unit/application/test_backtest.py`
  - 依存: 実データの蓄積量（mykeibadb 取り込み継続）

---

## 保留・ブロック中

- [ ] ⏸ **P2 統合テスト（testcontainers-postgres）の実行環境整備**
  - 状態: ⏸保留（Docker / DB 前提。CI or ローカルで要環境）
  - 対象: `apps/api/tests/integration/`
  - メモ: 現在は unit+contract のみ日常実行。infrastructure 層の実 DB 経路は integration 依存。
