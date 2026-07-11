# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-11（更新5回目・Claude→Codex 引き継ぎ） |
| 作業担当AI | Claude Code |
| 引き継ぎ先 | OpenAI Codex |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | `d840e66` feat(backtest): show track-type breakdown by default; decide RPCI accuracy policy |
| 作業ツリー | **クリーン**（`git status` = nothing to commit）。リモートと同期済み（ahead/behind 0） |
| 新規実装 | 本引き継ぎ作業では行っていない（依頼どおり現状整理のみ） |

---

## 現在の作業目的

直近の実質作業は「想定RPCI 精度の検証（受入基準 MAE≤1.5・展開ラベル一致率≥60% の達成度確認）」と、
その結果を受けた製品判断・ツール改善だった。これは**完了・コミット・プッシュ済み**。

本ターンは新規実装ではなく、**Claude Code → OpenAI Codex への引き継ぎ整理**のみを行った
（Git状態確認・差分の自己レビュー・テスト再実行・本ファイルおよび `tasks/current.md` の更新）。

---

## 完了した作業（直近セッション、すべてコミット・プッシュ済み）

1. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
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
2. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
3. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
4. **`forecast_accuracy` の UI 表示**（`e65f919`）: pace-analysis 画面に想定的中/相違を言葉と色で表示。
5. **AI 引き継ぎ基盤整備**（`004aead`）、**予測フィードバックループ**（`9712fd2`）ほか、
   それ以前の完了作業は `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

**なし。** 直近の依頼（想定RPCI精度検証 → 推奨方針の実行）は全て完了・検証・コミット・プッシュ済み。
`tasks/current.md`「進行中」「次に着手する候補」はいずれも空。次の作業はユーザー指示、または
下記候補から選ぶ形になる。

## 現在止まっている箇所

**なし。** 作業ツリーはクリーンで、途中状態のコード・未コミット差分は存在しない。
自然な区切り（= 次の作業を新規に開始してよいポイント）。

---

## 次に実施すべき作業（候補・優先順位順）

ユーザーからの新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する
（A節が方針決定済み、B節は着手可否に判断が必要、C節は技術的負債）。**どれを選ぶかは
ユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針に沿う）。

1. **P2 バックテスト結果の可視化/保存**（`tasks/backlog.md` A節）
   - 現状 `apps/api/scripts/backtest_forecast.py` は `print()` のみで結果を永続化しない。
   - 手順例: (a) `apps/api/src/pci/application/backtest.py` の `BacktestReport` をJSON化する
     関数を追加する、(b) `scripts/backtest_forecast.py` に `--output <path>` オプションを追加し
     結果をファイル保存できるようにする、(c) 的中率の推移を見たい場合はDBテーブル化も検討
     （ただし新テーブルはスコープが大きいため先にユーザーと方針確認）。
2. **P2 Windows ワーカー運用の監視強化**（`tasks/backlog.md` A節）
   - `ingest_log`（migration 002）は導入済みだが、失敗の可視化・再実行導線・
     `NOTIFY_WEBHOOK_URL` 通知の定着が未完了。
   - 手順例: (a) `apps/api/src/pci/presentation/routers/ingest.py` の `/internal/ingest/log`
     エンドポイントを使って直近の失敗一覧を返すエンドポイントを追加する案を検討、
     (b) `apps/ingestion-worker/src/ingestion/batch.py` の `_notify_failure()` が実際に
     Webhook通知するか手元で確認する。
3. **B節: 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO` 等）
   - 実データ検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行→結果を分析」の
     進め方になる可能性が高い。着手前にどの定数を対象にするかユーザーに確認する。
4. **C節: 技術的負債**（`mypy --strict` 全体化・統合テスト環境整備・旧handoffファイル整理等）
   - 優先度は相対的に低い。着手前にユーザーに確認。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 2026-07-11 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張 — `forecast_accuracy` 蓄積が増える、またはダートの外れに
  偏りが見えた場合に再検討。

---

## 変更対象ファイル（直近セッション、コミット `c94f708` + `d840e66` に含まれる。すべて反映済み）

- コード: `apps/api/src/pci/application/backtest.py`（`group_races_by_track`追加）,
  `apps/api/scripts/backtest_forecast.py`（`_print_track_breakdown`追加・docstring更新）,
  `apps/api/tests/unit/application/test_backtest.py`（`TestGroupRacesByTrack`追加）
- ドキュメント: `docs/DECISIONS.md`, `docs/SPEC.md`, `docs/adr/0005-rpci-forecast-strategy.md`,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`（本ファイル）

**本ターン（引き継ぎ整理）での変更**: `docs/HANDOFF.md`（本ファイル）, `tasks/current.md`
（優先順位・完了条件の明記）。コードは変更していない。

---

## 未確定仕様

- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかは未確定
  （`docs/SPEC.md §9`-3）。基準を定めた側（プロダクトオーナー）の確認が必要。
- ❓ PAI の正式定義・重み（pai-v1 は暫定、`docs/SPEC.md §9`-1）。
- ❓ 脚質判定ルールの最適化基準、展開コメントのLLM本採用可否、本番認証・課金仕様
  （いずれも `docs/SPEC.md §9` にリストあり、詳細はそちらを参照）。

## 仮実装

- 🧪 `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- 特になし（今回の変更でバグは発見・修正されていない。既存の未解決事項は下記「注意事項」参照）。

---

## テスト状況（本ターンで再実行・確認済み。2026-07-11時点）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `cd apps/api && python -m pytest tests/unit/ tests/contract/ -q` | **364 passed** |
| API Lint | `ruff check src/ tests/ scripts/` | 対象ファイルはclean（`scripts/seed_dev.py` に既存の無関係な10件あり・本セッション対象外・未着手） |
| API 型 | `mypy src/pci/domain/ src/pci/application/ --strict` | clean（27 files） |
| import境界 | `lint-imports` | 2 kept, 0 broken |
| Web 単体 | `cd apps/web && npm run test` | 55 passed（本セッションで web に変更なし） |

未実行: `tests/integration/`（testcontainers-postgres が必要。ローカル DB / Docker 前提）。
`apps/web`の`npm run typecheck`は前回セッション実行済みclean・本ターンは再実行していない
（webに変更がないため）。

失敗したテストはない。

---

## 注意事項

- **`pytest`単体コマンドはこの実行環境では `uv tool` の隔離環境（fastapi未インストール）を
  指す場合がある。** `python -m pytest` を使うこと（プロジェクトの依存関係が正しく解決される）。
  `which pytest` が `/root/.local/bin/pytest` を指す場合はこの問題に当たっている可能性が高い。
- このクラウド実行環境からは本番相当DB（mykeibadb蓄積データ）に**接続できない**。
  実データに対するバックテスト・検証系の作業はユーザーに手元（Windows機）で実行してもらい、
  出力を貼ってもらって分析する進め方になる。
- `backtest_forecast.py` の track別内訳表示は予測を2回実行するため、`--limit` を大きくすると
  実行時間が伸びる（上記「完了した作業」1.の既知のトレードオフ参照）。
- UI（Next.js）には PCI/RPCI/PAI の実数値を出さない方針（`docs/PROJECT_RULES.md §5`）。
  ただし CLI診断ツール（`backtest_forecast.py`等）は開発者向けであり、この方針の対象外
  （実数値をprintするのは意図的な挙動）。

---

## Codex が最初に読むべきファイル（順番）

1. `docs/HANDOFF.md`（このファイル）— 現状把握
2. `docs/PROJECT_RULES.md` — Claude/Codex 共通の遵守ルール（最重要）
3. `AGENTS.md` — Codex 固有の指示
4. `tasks/current.md` — 進行中タスク（現在は空。次候補は本ファイル「次に実施すべき作業」参照）
5. `docs/SPEC.md` — 確定/未確定仕様の区別
6. `docs/DECISIONS.md` — 直近の設計判断（特に2026-07-11の2件）
7. 必要に応じて `docs/ARCHITECTURE.md`, `docs/adr/0005-rpci-forecast-strategy.md`

## Codex が最初に実行すべきコマンド

```bash
# 1. 最新化・状態確認
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -10
git status   # クリーンであるはず

# 2. API 健全性確認（pytest ではなく python -m pytest を使うこと）
cd apps/api
python -m pytest tests/unit/ tests/contract/ -q
ruff check src/ tests/ scripts/
lint-imports
mypy src/pci/domain/ src/pci/application/ --strict

# 3. Web 健全性確認
cd ../web
npm run test
npm run typecheck
```
