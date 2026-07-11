# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-11（更新3回目） |
| 作業担当AI | Claude Code |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `8584e50` docs: move completed tasks out of tasks/current.md's in-progress section |
| 作業ツリー | 本更新時点でドキュメントのみ変更・未コミット（下記「変更対象ファイル」参照）。コード変更なし |

---

## 現在の目的

`tasks/current.md` の「次に着手する候補」に沿って、**想定RPCI 精度の検証**（受入基準
MAE≤1.5・展開ラベル一致率≥60% の達成度確認）を実施する。このクラウド実行環境からは
本番相当DB（mykeibadb蓄積データ）に接続できないため、ユーザーに手元（Windows機）で
`scripts/backtest_forecast.py` を実行してもらい、その出力をこちらで分析・記録した
（コード変更は伴わない、ドキュメント更新のみのセッション）。

---

## 完了した作業（直近セッション）

- **想定RPCI 精度の検証**（本セッション）: ユーザーが実DBで `python -m scripts.backtest_forecast`
  を3パターン（混合／芝／ダート、各--limit 200）実行、結果を分析して
  `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
  - MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332、過去15,440レースの実績と整合）。
  - ラベル一致率≥60% は芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。
  - **新知見**: 混合サンプルでの PAI point-biserial は+0.009（無相関に見える）だが、
    track別に分けると+0.084(芝)/+0.032(ダート)と過去記録どおりの正相関に戻る
    （母集団混在による希釈。Simpson のパラドックス類似）。今後のPAI検証は必ず
    `--track-type` を使うこと。
  - 「未達なら要因追加」の製品判断は未確定 → `tasks/current.md` 次候補へ。
- **`forecast_accuracy` の UI 表示**（`e65f919`）: pace-analysis 画面に想定的中/相違を
  言葉と色で表示するバッジを追加。実数値（RPCI・誤差）は出さない。予測未保存レースは非表示。
  ついでに `packages/api-client/src/schema.d.ts` の再生成漏れ（ingest_log 追加分）も解消。
- **AI 引き継ぎ基盤整備**（`004aead`）: PROJECT_RULES / ARCHITECTURE / SPEC / DECISIONS / HANDOFF /
  AGENTS.md / tasks/current.md / tasks/backlog.md / CLAUDE.md 追記。
- **予測フィードバックループ**（`9712fd2`）: 確定後の pace-analysis で、出走前の想定RPCI を
  引き当てて的中/外れを `forecast_accuracy` と回顧コメントに表示するAPI側の実装（後方互換）。
- **展開コメントの相性説明の明確化**（`b6a4a97`）、**好走実績の隣接レベルにじみ**（`c45143d`）、
  **取り込み自動化 & データ品質**（`e00333d`〜`d23cd96` 周辺）、**テストカバレッジ整備**（`3a9346d`〜）。

## 作業中の内容

なし（本セッションの検証・ドキュメント更新は完了。次にコミットする）。

## 次に実施する作業（候補）

1. 本セッションの変更をコミット・プッシュする（下記「変更対象ファイル」参照）。
2. **想定RPCI 受入基準の判定方針を決める**（`tasks/current.md` 次候補・ユーザー判断待ち）:
   現行モデルのまま運用継続か、追加投資（特徴量・学習データ拡張）をするか。
3. `backtest_forecast.py` の既定出力に track 別内訳を追加（PAI希釈の落とし穴を塞ぐ、P2）。
4. `tasks/backlog.md` の他の改善候補（暫定定数の検証等）から選ぶ。

---

## 変更対象ファイル（本セッション・コミット前）

- 更新（すべてドキュメントのみ・コード変更なし）: `docs/SPEC.md`（§8実測結果・§9未確定事項）,
  `docs/adr/0005-rpci-forecast-strategy.md`（§5.4 追記）, `tasks/current.md`（完了/次候補更新）,
  `tasks/backlog.md`（A節の完了反映・B節の数値更新）, `docs/HANDOFF.md`（本ファイル）

---

## 未解決事項 / 仮実装 / 既知の不具合

- 🧪 暫定値: `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- ❓ 想定RPCI 受入基準は**実測済み**（`docs/SPEC.md §8`）: MAE未達（構造的）・ラベル一致率は
  ダートのみ未達。「このまま運用継続か追加投資か」の製品判断は未確定（`tasks/current.md`）。
- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかも未確定（`SPEC.md §9`-3）。
- 🔎 PAI の効果検証は必ず `--track-type` を指定すること。混合集計は相関を希釈して見せる
  落とし穴がある（ADR-0005 §5.4）。
- 🔎 `mypy src/ --strict` は infrastructure/presentation で SQLAlchemy/Pydantic/FastAPI スタブ未導入により
  多数エラー（**環境要因・コード欠陥ではない**）。domain/application は strict clean。
- 旧 `docs/handoff-claude-code-2026-06-25.md` は一部ファイル名が現構成と異なる（歴史資料として残置）。
  現状は本 HANDOFF.md と `docs/ARCHITECTURE.md` を正とする。

---

## テスト実行状況（2026-07-11 時点・本セッション）

本セッションはドキュメント更新のみ（コード変更なし）のため、テスト・型・Lintの再実行は不要と判断。
直近のコード変更時点（`e65f919`）での実行結果は以下の通り。

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `cd apps/api && pytest tests/unit/ tests/contract/ -q` | 362 passed |
| Web 単体 | `cd apps/web && npm run test` | 55 passed |
| Web 型 | `cd apps/web && npm run typecheck` | clean |
| api-client 型 | `cd packages/api-client && npm run typecheck` | clean |

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
