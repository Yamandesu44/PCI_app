# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-11（更新4回目） |
| 作業担当AI | Claude Code |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `c94f708` docs: record RPCI forecast accuracy verification results |
| 作業ツリー | 本更新時点でドキュメント + `backtest.py`/`backtest_forecast.py`/テストが未コミット（下記参照） |

---

## 現在の目的

前セッションで実施した**想定RPCI 精度の検証**（`docs/SPEC.md §8`）を受け、ユーザーから
「推奨する選択肢」の実行を依頼された。以下2点を実施:

1. 受入基準未達（MAE構造的未達・ダートのラベル一致率未達）に対する当面の方針を決め、
   `docs/DECISIONS.md` に記録（製品判断: 追加投資せず現行モデル継続、見直し条件付き）。
2. 検証中に見つけた `backtest_forecast.py` の落とし穴（コース混合だとPAI相関が希釈されて
   見える）を塞ぐため、既定出力に track 別内訳を自動追加するコード変更を実施。

---

## 完了した作業（直近セッション）

- **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11）: 現行モデル
  （lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続、MAE≤1.5 を追う追加投資は今は行わない。
  UIは実数値非表示のためラベル一致率(33%ランダムを上回る)とPAIリフト(track別1.18〜1.32x)を
  実効性の根拠とした。見直し条件: `forecast_accuracy`蓄積増加、ダートの外れの偏り。
  受入基準の文言解釈（blended/track別）自体は別問題として `SPEC.md §9`-3 に残置（範囲外）。
- **`backtest_forecast.py` の track別内訳を既定表示に追加**（コード変更）:
  `application/backtest.py` に純粋関数 `group_races_by_track()` を追加、
  `scripts/backtest_forecast.py` に `_print_track_breakdown()` を追加。
  `--track-type` 未指定時、混合集計に加えて芝/ダート別の再集計も自動表示する
  （再予測はせず、既に読み込み済みの `targets` を分割して `ForecastBacktester.run()` を
  再実行するのみ。DB再クエリは発生しない）。テスト2件追加（`test_backtest.py`）。
- **想定RPCI 精度の検証**（`c94f708`）: ユーザーが実DBで `python -m scripts.backtest_forecast`
  を3パターン（混合／芝／ダート、各--limit 200）実行、結果を分析して
  `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
  - MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332、過去15,440レースの実績と整合）。
  - ラベル一致率≥60% は芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。
  - **新知見**: 混合サンプルでの PAI point-biserial は+0.009（無相関に見える）だが、
    track別に分けると+0.084(芝)/+0.032(ダート)と過去記録どおりの正相関に戻る
    （母集団混在による希釈。Simpson のパラドックス類似）。
- **`forecast_accuracy` の UI 表示**（`e65f919`）: pace-analysis 画面に想定的中/相違を
  言葉と色で表示するバッジを追加。実数値（RPCI・誤差）は出さない。予測未保存レースは非表示。
- **AI 引き継ぎ基盤整備**（`004aead`）: PROJECT_RULES / ARCHITECTURE / SPEC / DECISIONS / HANDOFF /
  AGENTS.md / tasks/current.md / tasks/backlog.md / CLAUDE.md 追記。
- **予測フィードバックループ**（`9712fd2`）: 確定後の pace-analysis で、出走前の想定RPCI を
  引き当てて的中/外れを `forecast_accuracy` と回顧コメントに表示するAPI側の実装（後方互換）。

## 作業中の内容

なし（本セッションの決定・コード変更・ドキュメント更新は完了。次にコミットする）。

## 次に実施する作業（候補）

1. 本セッションの変更をコミット・プッシュする（下記「変更対象ファイル」参照）。
2. `tasks/backlog.md` の改善候補（暫定定数の検証、バックテスト結果の可視化/保存等）から選ぶ。
3. 見直し条件（`forecast_accuracy`蓄積増加・ダートの外れの偏り）に該当したら、
   ダート特徴量追加の検討を再開する（`docs/DECISIONS.md`参照）。

---

## 変更対象ファイル（本セッション・コミット前）

- 更新（コード）: `apps/api/src/pci/application/backtest.py`（`group_races_by_track`追加）,
  `apps/api/scripts/backtest_forecast.py`（`_print_track_breakdown`追加・docstring更新）,
  `apps/api/tests/unit/application/test_backtest.py`（`TestGroupRacesByTrack`追加）
- 更新（ドキュメントのみ）: `docs/DECISIONS.md`（受入基準未達の方針を追記）,
  `docs/SPEC.md`（§8/§9更新）, `tasks/current.md`（完了反映）, `tasks/backlog.md`（完了反映）,
  `docs/HANDOFF.md`（本ファイル）

---

## 未解決事項 / 仮実装 / 既知の不具合

- 🧪 暫定値: `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 想定RPCI 受入基準の未達に対する方針は**暫定決定済み**（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討。
- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかは未確定（`SPEC.md §9`-3）。
  これは基準を定めた側（プロダクトオーナー）の確認が必要な、上記決定とは別軸の解釈問題。
- 🔎 PAI の効果検証は必ず `--track-type` を指定すること（対策済み: 既定出力に track別内訳を自動表示）。
- 🔎 `mypy src/ --strict` は infrastructure/presentation で SQLAlchemy/Pydantic/FastAPI スタブ未導入により
  多数エラー（**環境要因・コード欠陥ではない**）。domain/application は strict clean。
- 旧 `docs/handoff-claude-code-2026-06-25.md` は一部ファイル名が現構成と異なる（歴史資料として残置）。
  現状は本 HANDOFF.md と `docs/ARCHITECTURE.md` を正とする。

---

## テスト実行状況（2026-07-11 時点・本セッション）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `cd apps/api && python -m pytest tests/unit/ tests/contract/ -q` | **364 passed**（+2: group_races_by_track） |
| API Lint | `ruff check src/ tests/ scripts/` | 対象ファイルはclean（`scripts/seed_dev.py`に既存の無関係な10件あり・未着手） |
| API 型 | `mypy src/pci/domain/ src/pci/application/ --strict` | clean |
| import境界 | `lint-imports` | 2 kept, 0 broken |
| Web 単体 | `cd apps/web && npm run test` | 55 passed（本セッション変更なし） |

（統合テスト `tests/integration/` は testcontainers-postgres が必要。ローカル DB / Docker 前提。今回未実行）

**注記**: `pytest`単体コマンドは本環境で `uv tool` の隔離環境（fastapi未インストール）を指す場合がある。
`python -m pytest` を使うこと（プロジェクトの依存関係が正しく解決される）。

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
