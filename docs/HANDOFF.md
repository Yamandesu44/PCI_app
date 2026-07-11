# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-11（更新2回目） |
| 作業担当AI | Claude Code |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `004aead` docs: add Claude Code / Codex handoff foundation |
| 作業ツリー | 本更新時点で `forecast_accuracy` UI 表示一式が未コミット（下記「変更対象ファイル」参照） |

---

## 現在の目的

`tasks/current.md` の「次に着手する候補」に沿って、`forecast_accuracy`（予測 vs 実績の答え合わせ）
をフロントエンドに表示する。

---

## 完了した作業（直近セッション）

- **`forecast_accuracy` の UI 表示**（本セッション・未コミット）: pace-analysis 画面に想定的中/相違を
  言葉と色で表示するバッジを追加。実数値（RPCI・誤差）は出さない。予測未保存レースは非表示。
  ついでに `packages/api-client/src/schema.d.ts` の再生成漏れ（前回セッションの ingest_log 追加分含む）も解消。
- **AI 引き継ぎ基盤整備**（`004aead`）: PROJECT_RULES / ARCHITECTURE / SPEC / DECISIONS / HANDOFF /
  AGENTS.md / tasks/current.md / tasks/backlog.md / CLAUDE.md 追記。
- **予測フィードバックループ**（`9712fd2`）: 確定後の pace-analysis で、出走前の想定RPCI を
  引き当てて的中/外れを `forecast_accuracy` と回顧コメントに表示するAPI側の実装（後方互換）。
- **展開コメントの相性説明の明確化**（`b6a4a97`）、**好走実績の隣接レベルにじみ**（`c45143d`）、
  **取り込み自動化 & データ品質**（`e00333d`〜`d23cd96` 周辺）、**テストカバレッジ整備**（`3a9346d`〜）。

## 作業中の内容

なし（`forecast_accuracy` UI 表示は実装・検証済み。次にコミットする）。

## 次に実施する作業（候補）

1. 本セッションの変更をコミット・プッシュする（下記「変更対象ファイル」参照）。
2. 蓄積データで想定RPCI 精度（MAE/一致率）を確認し、rule-v4 の受入基準達成度を検証
   （`tasks/current.md` 次候補）。
3. `tasks/backlog.md` の改善候補（暫定定数の検証等）から選ぶ。

---

## 変更対象ファイル（本セッション・コミット前）

- 追加: `apps/web/src/components/ForecastAccuracyBadge.tsx`
- 更新: `packages/api-client/src/index.ts`（`ForecastAccuracy` 型エイリアス追加）,
  `packages/api-client/src/schema.d.ts`（再生成。`ForecastAccuracySchema` + 前回漏れの `IngestLogBody`/
  `IngestLogResponse`/`/internal/ingest/log` を反映）,
  `apps/web/src/lib/pace.ts`（`forecastAccuracyMeta` 追加）,
  `apps/web/src/lib/pace.test.ts`（テスト3件追加）,
  `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`（バッジ組み込み）,
  `apps/web/src/app/globals.css`（`.forecast-accuracy-badge*` スタイル追加）,
  `tasks/current.md`（本タスクを完了に更新）

---

## 未解決事項 / 仮実装 / 既知の不具合

- 🧪 暫定値: `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- ❓ 想定RPCI 受入基準（MAE≤1.5 / 一致率≥60%）の達成状況は未検証。芝「平均」再現率 0% の既知課題あり。
- 🔎 `mypy src/ --strict` は infrastructure/presentation で SQLAlchemy/Pydantic/FastAPI スタブ未導入により
  多数エラー（**環境要因・コード欠陥ではない**）。domain/application は strict clean。
- 旧 `docs/handoff-claude-code-2026-06-25.md` は一部ファイル名が現構成と異なる（歴史資料として残置）。
  現状は本 HANDOFF.md と `docs/ARCHITECTURE.md` を正とする。

---

## テスト実行状況（2026-07-11 時点・本セッション）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `cd apps/api && pytest tests/unit/ tests/contract/ -q` | 362 passed（本セッションでAPI変更なし） |
| Web 単体 | `cd apps/web && npm run test` | **55 passed**（+3: forecastAccuracyMeta） |
| Web 型 | `cd apps/web && npm run typecheck` | clean |
| api-client 型 | `cd packages/api-client && npm run typecheck` | clean |
| api-client 生成ドリフト | `cd packages/api-client && npm run generate && git diff` | 再生成実行済み・差分は今回のコミット対象 |

（統合テスト `tests/integration/` は testcontainers-postgres が必要。ローカル DB / Docker 前提。今回未実行）

---

## 次の担当者が最初に確認するファイル（順番）

1. `docs/HANDOFF.md`（このファイル）… 現状把握
2. `docs/PROJECT_RULES.md` … 守るべき共通ルール
3. `CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex）… ツール固有の指示
4. `tasks/current.md` … 進行中タスク
5. `docs/SPEC.md` … 確定/未確定仕様の区別
6. `docs/ARCHITECTURE.md` … 構成把握
7. 必要に応じて `docs/adr/`, `docs/design/`, `docs/DECISIONS.md`

---

## 作業再開時の推奨コマンド

```bash
# 1. 最新化
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -10
git status

# 2. API 健全性確認
cd apps/api
pytest tests/unit/ tests/contract/ -q
ruff check src/ tests/
lint-imports
mypy src/pci/domain/ src/pci/application/ --strict

# 3. Web 健全性確認
cd ../web
npm run test
npm run typecheck
```
