# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-12（Claude CodeがCodexの引き継ぎを検証し作業継続） |
| 作業担当AI | Claude Code |
| 直前の担当AI | OpenAI Codex（`4d9e5b5`〜`81ddb9d`の3実装+引き継ぎ文書を実施） |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `af66e8f` docs: verify Codex handoff and track formation-v1 weights for review |
| 作業ツリー | 本更新時点で `backtest_forecast.py --output` 機能一式が未コミット（下記「変更対象ファイル」参照） |
| 引き継ぎ検証結果 | Codexの実装3件を検証、重大な不整合なし（詳細は `tasks/current.md` 冒頭・Git履歴参照） |

---

## 現在の作業目的

Codexからの引き継ぎ内容（running-style-v2-distance / formation-v1 / UI刷新）を検証した上で、
`tasks/backlog.md` の最優先候補だった**バックテスト結果の可視化/保存**に着手した。

---

## 完了した作業（直近セッション、すべてコミット・プッシュ済み）

0. **Codex引き継ぎ内容の検証**（`af66e8f`、ドキュメントのみ）
   - ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従（無傷）。
   - `formation.py`のdomain純粋性・`has_confirmed_draw`のfrom_no=0前提（ingestion側の実装まで遡って
     確認）・`predict_running_style_for_distance`の新しさ重み付け（`find_horse_recent_entries`が
     新しい順を保証することをProtocol/実装/Fake全て確認）・UI差分全体のRPCI/PCI3/PAI実数値非露出、
     をコードレベルで検証。API全テスト・Web全テスト・OpenAPI/schema.d.ts再生成ドリフトなしを
     自分で再実行し、Codexの報告と一致することを確認（鵜呑みにせず独立再現）。
   - 軽微な指摘のみ（新規UIコンポーネントに専用テストなし＝既存方針通り、実DB数値は
     このクラウド環境から再現不能、等）。重大な不整合なし。

1. **バックテスト結果のJSON保存**（本セッション・未コミット）
   - `apps/api/src/pci/application/backtest.py` に `report_to_dict()`（+内部変換関数）を追加。
   - `apps/api/scripts/backtest_forecast.py` に `--output <path>` を追加。混合集計＋
     （`--track-type`未指定なら）track別内訳をJSONへ保存。既存の `print` 出力は変更なし。
   - DBテーブル化は見送り（推移ダッシュボードが要る段階で再検討、`tasks/backlog.md` A節）。
   - テスト: `TestReportToDict` 2件（`json.dumps`で実際にシリアライズ可能かも確認）。
     スクリプト層の実ファイル書き込みは手動スモークテストで確認（ユニットテスト対象外は既存方針通り）。
   - 検証: API 382 passed（+2）、ruff/mypy/lint-imports clean。

2. **混在型脚質の距離対応予測**（`2b083ba`、Codex実装・検証済み）
   - 直近20レース266頭を調査し、旧自在139頭のうち99頭が60%未満の混在、40頭が履歴なしと確認。
   - 明確な `running-style-v1` 判定は維持し、混在型だけ `running-style-v2-distance` で再判定。
   - 過去5走の4角位置、対象距離との距離差、近走順を使用。先行・差し同数時の距離規則を追加。
   - 予想日以後の成績を参照しないよう、履歴取得に開催日前カットオフを明示。
   - 同じ266頭で自在を139頭（52.3%）から40頭（15.0%）へ削減。履歴なしは参考のまま維持。
   - API 380件、Web 55件、ruff/mypy/import-linter/typecheck/buildがすべて成功。

3. **枠順確定後の隊列予想**（`c679e09`、Codex実装・検証済み）
   - `domain/pace/formation.py` に枠順確定判定と formation-v1 を追加。
   - 全馬の枠番が1〜8、馬番が正かつ一意の場合のみ予想し、特別登録（frame_no=0）は `null`。
   - 脚質70%・近走の1角（欠損時4角）位置30%で先頭/好位/中団/後方へ配置。
   - 各馬に日本語の根拠と「高・標準・参考」の信頼度ラベルを付与。
   - OpenAPI/API Clientを再生成し、WebにJRA枠色の `FormationView` を追加。
   - 契約テストの予測器をルールベースへ固定し、WindowsのLightGBMネイティブabortを回避。
   - 実DBで entries 278件、枠順確定112件は生成、未確定166件は非生成を確認。

4. **レース分析UIの刷新**（`4d9e5b5`、Codex実装・検証済み）
   - `AppHeader` を追加し、全画面でブランドとレース一覧への導線を固定。
   - レース一覧を最大幅拡張し、統計、開催日カレンダー、日付・競馬場別レースを2カラム化。
   - 展開予想と確定後回顧へ共通のダークヒーローとエメラルドのアクセントを導入。
   - 予想サマリー、初心者向け解説、展開恩恵馬、評価を下げたい馬の視覚階層を整理。
   - 回顧画面は「PCI判定」を「ペース傾向」へ翻訳し、内部実数値を新たに露出していない。
   - モバイルでは1カラム、デスクトップでは一覧のカレンダーをstickyサイドバーとして表示。

以下は以前の完了作業:

5. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
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
6. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
7. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
8. **`forecast_accuracy` の UI 表示**（`e65f919`）: pace-analysis 画面に想定的中/相違を言葉と色で表示。
9. **AI 引き継ぎ基盤整備**（`004aead`）、**予測フィードバックループ**（`9712fd2`）ほか、
   それ以前の完了作業は `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

**なし。** 本セッションの作業（Codex引き継ぎ検証＋バックテスト結果JSON保存）は実装・検証済み、
これからコミットする。`tasks/current.md`「進行中」は空。次の作業はユーザー指示、または
下記候補から選ぶ形になる。

## 現在止まっている箇所

**なし。** 作業ツリーはクリーンで、途中状態のコード・未コミット差分は存在しない。
自然な区切り（= 次の作業を新規に開始してよいポイント）。

---

## 次に実施すべき作業（候補・優先順位順）

ユーザーからの新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する
（A節が方針決定済み、B節は着手可否に判断が必要、C節は技術的負債）。**どれを選ぶかは
ユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針に沿う）。

1. **P2 Windows ワーカー運用の監視強化**（`tasks/backlog.md` A節）
   - `ingest_log`（migration 002）は導入済みだが、失敗の可視化・再実行導線・
     `NOTIFY_WEBHOOK_URL` 通知の定着が未完了。
   - 手順例: (a) `apps/api/src/pci/presentation/routers/ingest.py` の `/internal/ingest/log`
     エンドポイントを使って直近の失敗一覧を返すエンドポイントを追加する案を検討、
     (b) `apps/ingestion-worker/src/ingestion/batch.py` の `_notify_failure()` が実際に
     Webhook通知するか手元で確認する。
2. **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・`RuleWeights`・`PaiWeights`・
   `FormationWeights`・`DistanceStyleWeights` 等）
   - 実データ検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行→結果を分析」の
     進め方になる可能性が高い。着手前にどの定数を対象にするかユーザーに確認する。
3. **P3 技術的負債**（`mypy --strict` 全体化・統合テスト環境整備・旧handoffファイル整理等）
   - 優先度は相対的に低い。着手前にユーザーに確認。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張（2026-07-11決定） — `forecast_accuracy` 蓄積が増える、
  またはダートの外れに偏りが見えた場合に再検討。

---

## 変更対象ファイル（本セッション・コミット前）

- コード: `apps/api/src/pci/application/backtest.py`（`report_to_dict`等の変換関数を追加）,
  `apps/api/scripts/backtest_forecast.py`（`--output <path>` オプション追加）,
  `apps/api/tests/unit/application/test_backtest.py`（`TestReportToDict` 2件追加）
- 文書: `tasks/current.md`（完了反映・優先順位整理）, `tasks/backlog.md`（完了反映）,
  `docs/HANDOFF.md`（本ファイル）

（Codex実装分 `2b083ba`/`c679e09`/`4d9e5b5` の変更ファイル一覧は各コミットまたは
`docs/DECISIONS.md`/`docs/SPEC.md` の該当エントリ参照）

---

## 未確定仕様

- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかは未確定
  （`docs/SPEC.md §9`-3）。基準を定めた側（プロダクトオーナー）の確認が必要。
- ❓ PAI の正式定義・重み（pai-v1 は暫定、`docs/SPEC.md §9`-1）。
- ❓ 脚質判定ルールの最適化基準、展開コメントのLLM本採用可否、本番認証・課金仕様
  （いずれも `docs/SPEC.md §9` にリストあり、詳細はそちらを参照）。
- 🔎 formation-v1 の脚質70%・近走序盤位置30%と4ゾーン境界は実データ評価前の仮仕様
  （`tasks/current.md` の「暫定定数の検証と正式化」に追跡タスクあり）。

## 仮実装

- 🧪 `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 `FormationWeights`（脚質0.7・近走序盤位置0.3）。`formation-v1` として隔離済み。
- 🧪 `DistanceStyleWeights`（近走減衰・距離差・先行距離補正）。
  `running-style-v2-distance` として隔離済みで、隊列ゾーン一致率による再検証が必要。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- 特になし（今回の変更でバグは発見・修正されていない。既存の未解決事項は下記「注意事項」参照）。

---

## テスト状況（Claude Codeが2026-07-12に独立して再実行・確認）

Codex報告の数値は鵜呑みにせず全項目を自分で再実行し、一致することを確認した上で、
バックテストJSON保存機能の追加分も同じコマンドで再検証した。

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `python -m pytest tests/unit/ tests/contract/ -q` | **382 passed**（Codex報告380 + 本セッション+2） |
| API Lint | `ruff check src/ tests/`（Codexの実行範囲） | **成功** |
| API Lint（scripts含む） | `ruff check src/ tests/ scripts/` | **本セッション変更分は成功**。`scripts/seed_dev.py`に無関係な既存10件あり（前セッションから存在・未着手） |
| API 型 | `mypy src/pci/domain/ src/pci/application/ --strict` | **成功（28 files）** |
| import境界 | `lint-imports` | **2 kept, 0 broken** |
| Web 単体 | `cd apps/web && npm run test` | **55 passed** |
| Web 型 | `npm run typecheck` | **成功** |
| Web build | `npm run build` | **成功**（3ページ + not-found） |
| OpenAPI再生成ドリフト | `python scripts/export_openapi.py` → git diff | **差分なし** |
| schema.d.ts再生成ドリフト | `npm run generate` → git diff | **差分なし** |
| `--output`書き込み | 手動スモークテスト（JSON書き込み→読み込み） | **成功**（combined/by_track両方、日本語ラベル正しく保存） |

未実行: integration（Docker/testcontainers前提）。実DB依存の検証（Codexの隊列予想266頭調査等）は
このクラウド環境からDB接続できず再現不能（Codexの報告を字面通り記録するに留める）。

---

## 注意事項

- **`pytest`単体コマンドはこの実行環境では `uv tool` の隔離環境（fastapi未インストール）を
  指す場合がある。** `python -m pytest` を使うこと（プロジェクトの依存関係が正しく解決される）。
  `which pytest` が `/root/.local/bin/pytest` を指す場合はこの問題に当たっている可能性が高い。
- 今回はローカルPostgreSQLへ読み取り接続できた。mykeibadb MySQLの再取り込みやWindows固有処理は、
  引き続きユーザー環境での実行が必要。
- `backtest_forecast.py` の track別内訳表示は予測を2回実行するため、`--limit` を大きくすると
  実行時間が伸びる（上記「完了した作業」5.の既知のトレードオフ参照）。
- UI（Next.js）には PCI/RPCI/PAI の実数値を出さない方針（`docs/PROJECT_RULES.md §5`）。
  ただし CLI診断ツール（`backtest_forecast.py`等）は開発者向けであり、この方針の対象外
  （実数値をprintするのは意図的な挙動）。

---

## 次の担当者が最初に読むべきファイル（順番）

1. `docs/HANDOFF.md`（このファイル）— 現状把握
2. `docs/PROJECT_RULES.md` — Claude/Codex 共通の遵守ルール（最重要）
3. `CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex）— ツール固有の指示
4. `tasks/current.md` — 進行中タスク（現在は空。次候補は本ファイル「次に実施すべき作業」参照）
5. `docs/SPEC.md` — 確定/未確定仕様の区別
6. `docs/DECISIONS.md` — 直近の設計判断（2026-07-12の formation-v1/running-style-v2-distance の2件）
7. 必要に応じて `docs/ARCHITECTURE.md`, `docs/adr/0005-rpci-forecast-strategy.md`

## 次の担当者が最初に実行すべきコマンド

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
