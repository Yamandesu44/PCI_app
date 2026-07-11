# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-11 |
| 作業担当AI | Claude Code |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | `9712fd2` feat(api): close the forecast feedback loop with predicted-vs-actual review |
| 作業ツリー | クリーン（このコミット時点。引き継ぎ基盤ファイルは本更新で追加） |

---

## 現在の目的

AI 間（Claude Code / Codex）の引き継ぎ基盤を整備し、会話履歴に依存せず作業状態を復元できるようにする。
（＝この HANDOFF.md を含む一連のドキュメント整備そのものが直近の作業）

---

## 完了した作業（直近セッション）

- **予測フィードバックループ**（`9712fd2`）: 確定後の pace-analysis で、出走前の想定RPCI を
  引き当てて的中/外れを `forecast_accuracy` と回顧コメントに表示。後方互換（未保存なら null）。
- **展開コメントの相性説明の明確化**（`b6a4a97`）: ピークと今回レベルが異なるが今回レベルにも
  実績がある馬の説明文を分岐。
- **好走実績の隣接レベルにじみ**（`c45143d`）: 隣接ペースレベルを誤って「不安(0点)」にしない補正。
- **取り込み自動化 & データ品質**（`e00333d`〜`d23cd96` 周辺）: mykeibadb 経路の Task Scheduler 自動化、
  上がり3F 異常値の除外、`ingest_log` 記録、手動同期 runbook（`apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`）。
- **テストカバレッジ整備**（`3a9346d`〜）: domain/pace ほぼ 100%、application 高水準。

## 作業中の内容

- **引き継ぎ基盤ドキュメントの新規作成**（このコミットで完了予定）:
  `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
  `docs/HANDOFF.md`, `AGENTS.md`, `tasks/current.md`, `tasks/backlog.md`、および `CLAUDE.md` への追記。

## 次に実施する作業（候補）

1. フロントで `forecast_accuracy` を表示する UI（的中/外れバッジ）。表示は言葉/色で（実数値を出さない）。
2. 蓄積データで想定RPCI 精度（MAE/一致率）を確認し、rule-v4 の受入基準達成度を検証。
3. `tasks/current.md` / `tasks/backlog.md` を参照して優先タスクを選ぶ。

---

## 変更対象ファイル（本引き継ぎ整備で追加/更新）

- 追加: `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
  `docs/HANDOFF.md`, `AGENTS.md`, `tasks/current.md`, `tasks/backlog.md`
- 更新: `CLAUDE.md`（AI 協働運用セクションを追記）

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

## テスト実行状況（2026-07-11 時点・コミット 9712fd2）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `cd apps/api && pytest tests/unit/ tests/contract/ -q` | 362 passed |
| API Lint | `cd apps/api && ruff check src/ tests/` | clean |
| 依存方向 | `cd apps/api && lint-imports` | 2 contracts kept |
| 型（domain+application） | `cd apps/api && mypy src/pci/domain/ src/pci/application/ --strict` | clean |
| Web 単体 | `cd apps/web && npm run test` | 52 passed |
| Web 型 | `cd apps/web && npm run typecheck` | clean |

（統合テスト `tests/integration/` は testcontainers-postgres が必要。ローカル DB / Docker 前提）

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
