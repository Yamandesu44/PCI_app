# HANDOFF — 現在の作業状態

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-12（更新3回目・取り込み鮮度監視 実装） |
| 作業担当AI | Claude Code |
| 直前の担当AI | OpenAI Codex（`4d9e5b5`〜`81ddb9d`の3実装+引き継ぎ文書を実施。検証済み・不整合なし） |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | 本更新をコミットする直前は `3d3131e` feat(forecast): compute per-style pace advantage in domain |
| 作業ツリー | 本更新時点で取り込み鮮度監視（ingest-status）一式が未コミット（下記「変更対象ファイル」参照） |

---

## 現在の作業目的

ユーザーから実利用のフィードバックを受け、2点対応した:
① 展開分析の脚質別有利度が高止まりして差が出ない（`3d3131e` で修正済み）。
② 展開恩恵馬のピックアップに加えて絶対能力も加味した順位予想が欲しい → ユーザー判断で保留
（`tasks/backlog.md` B節、能力指数の算出方法自体の模索が必要なため）。

保留②を受け、「他に実施すべき改善」の相談から**推奨1: データ取り込みの監視・鮮度表示**に着手した。

---

## 完了した作業（直近セッション）

1. **データ取り込みの鮮度監視**（本セッション・未コミット）
   - 背景: `ingest_log` は書き込み専用で、自動同期が静かに失敗し続けても気づけなかった。
   - 対応: 新規 `domain/ops/ingest_log.py`（`IngestLogRepository` Protocol + 純粋関数
     `evaluate_freshness()`）。判定は「直近試行の失敗有無」「直近成功からの経過日数
     （暫定閾値 `STALE_AFTER_DAYS=4`）」のみで、Task Schedulerの具体的cronはコードに埋め込まない。
     `GET /api/v1/ingest-status`（公開GET、`/internal/ingest/*`の認証とは別）を新設し、
     web トップに `IngestStatusBanner`（正常時は控えめ、鮮度低下・失敗時のみ目立つ配色、
     失敗一覧は開閉式で最大5件・エラー要約200文字まで）を追加。
   - ログが1件も無い環境（開発/fixture等）は `has_history=False` とし「異常」ではなく
     「監視対象外」として扱い、誤警告を防ぐ。
   - **未実施（ユーザー環境でのみ確認可能）**: `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に
     届くかの実地確認。画面からの手動再実行導線も未着手（`tasks/backlog.md` A節に残課題として記録）。

2. **脚質別有利度の修正（style-advantage-v1）**（`3d3131e`）
   - 原因: web が「その脚質の最大PAI」を有利度に流用しており、スコアが60〜96に高止まり。
   - 対応: `domain/pace/style_advantage.py` 新設。想定RPCIの中立点（classify_pace と同じ
     rule-v4 閾値の中点: 芝50/ダート43）からの乖離を 50=互角の対称スコア（0〜100）へ写像。
     逃げ・追込は増幅1.2、逃げ候補2頭以上で逃げのみ競合減点。reasons/model_version 付き。
   - `StyleAdvantageWeights` は🧪仮係数（`docs/SPEC.md §3.4/§9`-11、`docs/DECISIONS.md` 2026-07-12）。

3. **バックテスト結果のJSON保存**（`03bc005`）
   - `report_to_dict()` + `--output <path>`。混合＋track別内訳をJSON保存。print出力は不変。

4. **Codex引き継ぎ内容の検証**（`af66e8f`、ドキュメントのみ）
   - ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従（無傷）。
   - Codexの実装3件をコードレベルで検証し、テストを独立再実行。重大な不整合なし。

5. **混在型脚質の距離対応予測**（`2b083ba`、Codex実装・検証済み）
   - 直近20レース266頭を調査し、旧自在139頭のうち99頭が60%未満の混在、40頭が履歴なしと確認。
   - 明確な `running-style-v1` 判定は維持し、混在型だけ `running-style-v2-distance` で再判定。
   - 過去5走の4角位置、対象距離との距離差、近走順を使用。先行・差し同数時の距離規則を追加。
   - 予想日以後の成績を参照しないよう、履歴取得に開催日前カットオフを明示。
   - 同じ266頭で自在を139頭（52.3%）から40頭（15.0%）へ削減。履歴なしは参考のまま維持。
   - API 380件、Web 55件、ruff/mypy/import-linter/typecheck/buildがすべて成功。

6. **枠順確定後の隊列予想**（`c679e09`、Codex実装・検証済み）
   - `domain/pace/formation.py` に枠順確定判定と formation-v1 を追加。
   - 全馬の枠番が1〜8、馬番が正かつ一意の場合のみ予想し、特別登録（frame_no=0）は `null`。
   - 脚質70%・近走の1角（欠損時4角）位置30%で先頭/好位/中団/後方へ配置。
   - 各馬に日本語の根拠と「高・標準・参考」の信頼度ラベルを付与。
   - OpenAPI/API Clientを再生成し、WebにJRA枠色の `FormationView` を追加。
   - 契約テストの予測器をルールベースへ固定し、WindowsのLightGBMネイティブabortを回避。
   - 実DBで entries 278件、枠順確定112件は生成、未確定166件は非生成を確認。

7. **レース分析UIの刷新**（`4d9e5b5`、Codex実装・検証済み）
   - `AppHeader` を追加し、全画面でブランドとレース一覧への導線を固定。
   - レース一覧を最大幅拡張し、統計、開催日カレンダー、日付・競馬場別レースを2カラム化。
   - 展開予想と確定後回顧へ共通のダークヒーローとエメラルドのアクセントを導入。
   - 予想サマリー、初心者向け解説、展開恩恵馬、評価を下げたい馬の視覚階層を整理。
   - 回顧画面は「PCI判定」を「ペース傾向」へ翻訳し、内部実数値を新たに露出していない。
   - モバイルでは1カラム、デスクトップでは一覧のカレンダーをstickyサイドバーとして表示。

以下は以前の完了作業:

8. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
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
9. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
10. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
11. **`forecast_accuracy` の UI 表示**（`e65f919`）、**AI 引き継ぎ基盤整備**（`004aead`）、
    **予測フィードバックループ**（`9712fd2`）ほか、それ以前の完了作業は
    `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

- ユーザー要望②「**展開＋絶対能力の統合順位予想**」は保留中（ユーザー判断・`tasks/backlog.md` B節）。
  能力指数の算出方法自体の模索が必要なため。再開時はまず指標案をユーザーへ提示して合意を取ること。
- **Windows実行機での実地確認が必要な残課題**（このクラウド環境からは検証不可）:
  `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に届くか。
- 画面からの手動再実行導線は未着手（`tasks/backlog.md` A節。多重実行防止等の設計が必要）。
- それ以外はなし。①（脚質別有利度）・監視強化（推奨1）とも実装・検証済みでこれからコミットする。

## 現在止まっている箇所

**なし。** 取り込み鮮度監視一式は検証済みでコミット待ちの状態。

---

## 次に実施すべき作業（候補・優先順位順）

ユーザーからの新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する
（A節が方針決定済み、B節は着手可否に判断が必要、C節は技術的負債）。**どれを選ぶかは
ユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針に沿う）。

1. **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・`RuleWeights`・`PaiWeights`・
   `FormationWeights`・`DistanceStyleWeights`・`StyleAdvantageWeights`・`STALE_AFTER_DAYS` 等）
   - 実データ・実運用での検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行/
     しばらく運用→結果を分析」の進め方になる可能性が高い。着手前にどの定数を対象にするか確認する。
2. **P3 技術的負債**（`mypy --strict` 全体化・統合テスト環境整備・旧handoffファイル整理等）
   - 優先度は相対的に低い。着手前にユーザーに確認。

**保留・確認待ちの項目**:
- **P1 展開＋絶対能力の統合順位予想**（`tasks/backlog.md` B節・ユーザー要望2026-07-12）
  — ユーザー判断で保留中。再開の合図があれば、能力指数の定義案（例: 直近N走の着順/クラス/
  持ち時計/上がり順位の合成）を提示するところから始める。
- 画面からの手動再実行導線（`tasks/backlog.md` A節）— 要判断（安全性・多重実行防止の設計）。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張（2026-07-11決定） — `forecast_accuracy` 蓄積が増える、
  またはダートの外れに偏りが見えた場合に再検討。

---

## 変更対象ファイル（本セッション・コミット前）

- API: `apps/api/src/pci/domain/ops/`（新規パッケージ: `ingest_log.py`, `__init__.py`）,
  `infrastructure/repositories/ingest_log_repository.py`（新規）, `application/dto.py`,
  `application/ingest_status_use_cases.py`（新規）, `presentation/schemas.py`,
  `presentation/routers/status.py`（新規）, `presentation/dependencies.py`, `presentation/app.py`
- テスト: `tests/unit/domain/ops/test_ingest_log.py`（新規10件）,
  `tests/unit/application/test_ingest_status_use_cases.py`（新規5件）,
  `tests/unit/application/fake_ingest_log_repository.py`（新規）,
  `tests/contract/test_status_api.py`（新規3件）, `tests/contract/conftest.py`（fixture拡張）
- 生成物: `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`（再生成）,
  `packages/api-client/src/index.ts`（`IngestStatus`/`IngestFailure`型 + `getIngestStatus()`追加）
- Web: `apps/web/src/lib/ingestStatus.ts`（新規、翻訳層）, `apps/web/src/lib/ingestStatus.test.ts`（新規6件）,
  `apps/web/src/components/IngestStatusBanner.tsx`（新規）, `apps/web/src/app/page.tsx`（バナー組み込み）
- 文書: `docs/SPEC.md`（§5/§6.1/§9）, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`（本ファイル）

（style-advantage-v1 の変更ファイル一覧はコミット `3d3131e`、Codex実装分
`2b083ba`/`c679e09`/`4d9e5b5` の変更ファイル一覧は各コミットまたは
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
- 🔎 `STALE_AFTER_DAYS=4`（取り込み鮮度監視の暫定閾値）が実運用（週3回同期）に対して
  適切かは、しばらく運用してから検証する（`docs/SPEC.md §9`-13）。

## 仮実装

- 🧪 `RuleWeights`(rule-v4)・`PaiWeights`(pai-v1)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 `FormationWeights`（脚質0.7・近走序盤位置0.3）。`formation-v1` として隔離済み。
- 🧪 `DistanceStyleWeights`（近走減衰・距離差・先行距離補正）。
  `running-style-v2-distance` として隔離済みで、隊列ゾーン一致率による再検証が必要。
- 🧪 `StyleAdvantageWeights`（勾配4.0/pt・逃げ追込増幅1.2・逃げ競合減点6.0/頭）。
  `style-advantage-v1` として隔離済み（`docs/SPEC.md §9`-11）。
- 🧪 `STALE_AFTER_DAYS=4`（取り込み鮮度監視、`domain/ops/ingest_log.py`。本セッション追加）。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- 特になし（今回の変更でバグは発見・修正されていない。既存の未解決事項は下記「注意事項」参照）。

---

## テスト状況（2026-07-12・取り込み鮮度監視 実装後）

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `python -m pytest tests/unit/ tests/contract/ -q` | **414 passed**（+18: ops domain 10 + application 5 + contract 3） |
| API Lint | `ruff check src/ tests/` | **成功**（`scripts/seed_dev.py`に無関係な既存10件あり・未着手） |
| API 型 | `mypy src/pci/domain/ src/pci/application/ --strict` | **成功（32 files）** |
| import境界 | `lint-imports` | **2 kept, 0 broken**（domain/ops も含め依存方向OK） |
| api-client 型 | `cd packages/api-client && npm run typecheck` | **成功** |
| Web 単体 | `cd apps/web && npm run test` | **63 passed**（+6: ingestStatusMeta） |
| Web 型 | `npm run typecheck` | **成功** |
| Web build | `npm run build` | **成功**（3ページ + not-found） |
| OpenAPI | `python scripts/export_openapi.py` 実行済み | 差分はコミット対象（IngestStatusSchema等追加） |

未実行: integration（Docker/testcontainers前提）。実DB依存の検証（実運用での鮮度判定の
振る舞い、Webhook通知の到達確認）はこのクラウド環境から不可。ユーザーの実環境での確認を推奨。

---

## 注意事項

- **`pytest`単体コマンドはこの実行環境では `uv tool` の隔離環境（fastapi未インストール）を
  指す場合がある。** `python -m pytest` を使うこと（プロジェクトの依存関係が正しく解決される）。
  `which pytest` が `/root/.local/bin/pytest` を指す場合はこの問題に当たっている可能性が高い。
- このクラウド実行環境からは本番相当DB（mykeibadb蓄積データ）に**接続できない**。
  実データに依存する検証（バックテスト・実運用での鮮度判定・Webhook到達確認等）は
  ユーザーに手元（Windows機）で実行してもらい、出力を貼ってもらって分析する進め方になる。
- `backtest_forecast.py` の track別内訳表示は予測を2回実行するため、`--limit` を大きくすると
  実行時間が伸びる（上記「完了した作業」8.の既知のトレードオフ参照）。
- UI（Next.js）には PCI/RPCI/PAI の実数値を出さない方針（`docs/PROJECT_RULES.md §5`）。
  ただし CLI診断ツール（`backtest_forecast.py`等）は開発者向けであり、この方針の対象外
  （実数値をprintするのは意図的な挙動）。取り込み鮮度監視の失敗詳細（エラー要約）も、
  対象がPCI/RPCI等の指標ではなく運用ログのため同ルールの対象外（運用者本人向け情報）。

---

## 次の担当者が最初に読むべきファイル（順番）

1. `docs/HANDOFF.md`（このファイル）— 現状把握
2. `docs/PROJECT_RULES.md` — Claude/Codex 共通の遵守ルール（最重要）
3. `CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex）— ツール固有の指示
4. `tasks/current.md` — 進行中タスク（現在は空。次候補は本ファイル「次に実施すべき作業」参照）
5. `docs/SPEC.md` — 確定/未確定仕様の区別
6. `docs/DECISIONS.md` — 直近の設計判断（2026-07-12の4件: ingest-status鮮度監視・
   style-advantage-v1・formation-v1・running-style-v2-distance）
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
