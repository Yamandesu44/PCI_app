# tasks/current.md — 進行中タスク

> 進行中・直近着手のタスクをチェックボックスで管理する。着手/完了のたびに更新する。
> 状態: ⬜未着手 / 🔄進行中 / ✅完了 / ⏸保留。優先度: P0(必須) / P1(高) / P2(中) / P3(低)。
> 単なる改善案・未着手の候補は `tasks/backlog.md` に置く。

最終更新: 2026-07-11 / 担当: Claude Code / ブランチ `claude/sweet-einstein-ilnaov`

---

## 進行中

- [x] 🔄→✅ **P1 AI 引き継ぎ基盤の整備**
  - 状態: ✅ 完了（このコミット）
  - 対象: `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
    `docs/HANDOFF.md`, `AGENTS.md`, `tasks/current.md`, `tasks/backlog.md`, `CLAUDE.md`(追記)
  - 完了条件: 8ファイル作成 + CLAUDE.md 追記、実コードと矛盾なし、テスト/型/Lint green
  - 関連テスト: なし（ドキュメントのみ）。既存の API 362 / Web 52 が green のままであること
  - 依存: なし

---

## 次に着手する候補（今スプリントの当面）

- [ ] **P1 `forecast_accuracy` の UI 表示**
  - 状態: ⬜未着手
  - 対象: `apps/web/src/components/`（回顧画面）, `apps/web/src/lib/pace.ts`, `packages/api-client`
  - 完了条件: pace-analysis 画面に「想定が的中/外れ」を**言葉・色**で表示（実数値を出さない）。
    予測未保存レースではバッジ非表示。vitest 追加。
  - 関連テスト: `apps/web/src/lib/*.test.ts`
  - 依存: `9712fd2`（API 側 `forecast_accuracy` 実装済み）

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
