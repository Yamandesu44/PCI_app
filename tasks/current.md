# tasks/current.md — 進行中タスク

## 2026-07-23 完了: 重複レース450組の正規キー統合完了

- [x] 予想martを持つ旧キーは、正規側の同一モデル世代・全頭分カバレッジを検証する。
- [x] 残存していた2026-02-01東京9Rを正規キーへ再同期し、旧キーを削除した。
- [x] 統合後も正規キーの12頭、`predicted_pace` 1件、`pace_fit` 12件を維持した。
- [x] 直近1年の重複レース組数が0件になったことを実DBで確認した。

## 2026-07-23 完了: 重複レース449組の安全な正規キー統合

- [x] 正規キーの出走表・成績登録成功後だけ旧キーを削除する順序へ修正した。
- [x] 旧キー監査署名、正規頭数・確定頭数、中核成績一致、旧martゼロをAPIで再検証する。
- [x] 専用CLIはdry-runを既定とし、適用時は確認済み対象組数の指定を必須にした。
- [x] 実DBで449組を再同期し、旧キー449件を失敗0件で削除した。
- [x] 重複450組から1組へ削減。予想martを持つ東京9Rは安全側で保留した。

## 2026-07-23 完了: 重複レース統合前のdry-run監査

- [x] 認証付き`GET /internal/ingest/duplicate-race-audit`で、重複キーごとの状態・頭数・
  確定頭数・出走馬署名・中核成績署名・予想mart件数を読み取り専用で取得可能にした。
- [x] `python -m ingestion.audit_duplicate_races`でmykeibadbの`RACE_CODE`を正規キー候補とし、
  5区分へ分類するJSON監査CLIを追加した。
- [x] 2025-07-23〜2026-07-23を実DBで監査し、450組すべてで正規キーを一意に特定した。
- [x] 450組すべてが中核成績一致・旧キー側予想martなしの`removable_after_resync`だった。
- [x] 450組すべてで出走馬構成差があるため、正規キー再同期前の旧キー削除は禁止する。

## 2026-07-23 完了: 重複レースのデータ完全性監視

- [x] 直近365日のJRA平地について、同一開催日・競馬場・R番号に複数キーがあるレース組をDB集計する。
- [x] `/api/v1/ingest-status`へ重複組数と代表20組を追加し、Web警告バナーで各キーを確認可能にする。
- [x] 実DBで450組を検出し、監視が実データを捉えることを確認した。
- [x] FKを伴う誤削除を防ぐため、自動削除・自動統合は実装しない。

## 2026-07-23 完了: 小倉芝1200mの馬場状態別再検証

- [x] 確定値診断へ `distance-track-condition` 内訳を追加し、距離と馬場状態の交差条件を同時比較できるようにした。
- [x] 実DBの2025-07-01〜2026-07-31、小倉芝199レース・1534頭を再検証した。
- [x] 小倉芝1200mは良-22.4pt（45R）、稍重-10.5pt（12R）、重-9.0pt（6R）で、確認できた全馬場状態で逆転傾向が継続した。
- [x] `style-advantage-v3`の「7月・小倉・芝・1200m」を`reference`とする条件と仮係数は変更しない。
- [x] 参考表示の理由へ、馬場状態別でも同じ傾向であることを追記した。

## 2026-07-23 完了: 検証サマリー余白・馬場情報補完

- [x] 「事前の展開想定と実際の流れ」に `px-4 sm:px-6` を追加し、左右の見切れを解消した。
- [x] mykeibadb の `race-metadata` を定期フル同期と `--step all --mode mykeibadb` に組み込んだ。
- [x] コース種別・馬場状態・天候を既存レースへ補完できるようにした。
- [x] 旧形式レースキーと正規キーが併存する場合、日付・競馬場・R番号が一致する重複レースへ同じ補足情報を反映するようにした。
- [x] TrackCD の正式区分を mykeibadb の `track_code` マスタに合わせ、芝=10〜22、ダート=23〜29、障害=51〜59へ修正した。
- [x] 2025-07-23〜2026-07-23を再補完し、馬場情報未反映を564件から0件へ削減した。
- [x] mykeibadbに存在しない開発用シード `2026061805010101` をローカルDBから削除した。

現在の進行中タスク: なし。

> 進行中・直近着手のタスクをチェックボックスで管理する。着手/完了のたびに更新する。
> 状態: ⬜未着手 / 🔄進行中 / ✅完了 / ⏸保留。優先度: P0(必須) / P1(高) / P2(中) / P3(低)。
> 単なる改善案・未着手の候補は `tasks/backlog.md` に置く。

最終更新: 2026-07-23（重複レース450組の正規キー統合完了） / 担当: OpenAI Codex / ブランチ `claude/sweet-einstein-ilnaov`

詳しい状態は `docs/HANDOFF.md` を参照（このファイルはタスクの一覧管理に専念する）。

---

## 進行中

なし。

---

## 最近完了したタスク

- [x] ✅ **P2 予想検証を直前の同期間と比較する**
  - 選択中の30日・90日・180日の直前にある同じ日数を、重複しない比較期間として集計する。
  - 全体・芝・ダートについて前期間の一致率と母数を公開APIへ追加し、内部PCI/RPCI値は返さない。
  - Webトップの各指標へ前期比をポイント差・アイコン・色で表示し、比較元0件は「前期比較なし」とする。
  - 任意の良否閾値や自動評価は導入しない。
  - 検証: API対象11 passed、OpenAPIスナップショット2 passed、Web 74 passed、
    API Ruff・mypy strict、api-client/Web typecheck、Web build成功。First Load JSは110KBを維持。
- [x] ✅ **P2 予想検証の集計期間を30日・90日・180日で切り替える**
  - `GET /api/v1/forecast-performance?days=`へ許容期間を追加し、未指定時は従来どおり90日とした。
  - 一致率・信頼度別集計・外れ方向・カバー率は選択期間で再集計し、週次グラフは比較軸を揃えるため
    期間にかかわらず直近8完了週を維持する。
  - Webトップへセグメント切り替えを追加し、期間変更と開催日変更の双方でURL状態を保持する。
  - 検証: API対象11 passed、OpenAPIスナップショット2 passed、Web 74 passed、
    API Ruff・mypy strict、api-client/Web typecheck、Web build成功。First Load JSは110KBを維持。
- [x] ✅ **P1 事前予想を照合できた母集団カバー率を表示する**
  - 直近90日の確定済みJRA平地かつ実績展開を判定できるレース総数を、予想保存とは独立に集計する。
  - 照合済み件数／評価対象総数とカバー率を公開APIへ追加し、一致率の母集団偏りを判断可能にした。
  - Webトップでは完全なら緑、未保存が残る場合は黄の進捗バーで表示する。任意の品質閾値は設けない。
  - 検証: 新規API単体・契約7 passed、PostgreSQL統合1 passed、Web 74 passed、
    API Ruff・mypy strict、api-client/Web typecheck、Web build成功。First Load JSは110KBを維持。
- [x] ✅ **P2 予想と実績の展開3区分を比較し、外れ方の方向を可視化する**
  - 速い・平均・落ち着くの予想3区分を行、実績3区分を列とする混同行列をAPIへ追加した。
  - 各セルは件数と予想区分内割合だけを返し、PCI/RPCIの内部実数値は公開しない。
  - Webトップでは「外れ方の傾向」として既定で閉じ、一致セルと不一致セルを色分けする。
  - 検証: 新規API単体・契約7 passed、Web 74 passed、API Ruff・mypy strict、
    api-client/Web typecheck、Web build成功。First Load JSは110KBを維持。
- [x] ✅ **P2 表示上の信頼度区分ごとに展開予想一致率を検証する**
  - 既存UIと同じ「読みやすい（70%以上）」「標準（50%以上）」「変動注意（50%未満）」で集計する。
  - 各区分の一致率・的中数・母数を公開APIへ追加し、内部実数値は公開しない。
  - Webトップへ3本の比較バーを追加し、週次推移とデスクトップ2列・モバイル縦並びで表示する。
  - 検証: 新規API単体・契約7 passed、Web 74 passed、API Ruff・mypy strict、
    api-client/Web typecheck、Web build成功。First Load JSは110KBを維持。
- [x] ✅ **P2 展開予想一致率を直近8完了週の推移で可視化する**
  - 進行中の週を除外し、月曜から日曜までの完了週を8区間集計する。
  - 各週の一致率・的中数・母数を公開APIへ追加し、PCI/RPCI内部実数値は公開しない。
  - WebトップへRecharts棒グラフと最新週の母数を追加。グラフは遅延読み込みし、
    一覧の初期JSを110KBに維持した。
  - 検証: 新規API単体・契約7 passed、Web 74 passed、API Ruff・mypy strict、
    api-client/Web typecheck、Web build成功。
- [x] ✅ **P1 保存済み事前予想の展開一致率をレース一覧へ表示する**
  - 直近90日の確定済みJRA平地を対象に、レースごとの最新の有効な事前予想と実際の展開区分を比較する。
  - 全体・芝・ダートの一致率と検証レース数を`GET /api/v1/forecast-performance`で返す。
  - Webトップへ期間・母数付きの検証サマリーを追加し、PCI/RPCIの内部実数値は公開しない。
  - 同日内のレース終了後生成は時刻情報がないため完全には除外できず、運用上は事前生成を前提とする。
  - 検証: 新規API単体・契約7 passed、PostgreSQL統合1 passed、Web 74 passed、
    API Ruff・mypy strict、api-client/Web typecheck、Web build成功。
- [x] ✅ **P2 馬場状態バックフィルの完了判定をデータ完全性監視へ統合する**
  - 直近365日の確定済みJRA平地で`track_condition`欠損をDB集計し、代表20件を返す。
  - Webトップで成績未取込と区別して警告し、専用`race-metadata`コマンドをコピー可能にした。
  - `run_batch.ps1`へ`-ChunkDays`を追加し、1年分を7日単位で安定して処理できるようにした。
  - 実DBへのバックフィル実行と馬場別再検証は引き続きWindows実行機で行う。
- [x] ✅ **P2 mykeibadbの馬場状態・天候を永続化し、既存レースを安全にバックフィル可能にする**
  - `race_shosai`の芝/ダート馬場状態・天候コードを、固定長位置を介さない補足情報として読む。
  - 通常のentries/results同期へ自動反映し、既存レース専用`--step race-metadata`も追加。
  - 専用APIはレース状態・成績・出走馬・RPCI/PCI3を保持し、補足情報だけを更新する。
  - 実DBバックフィルと馬場別再検証はWindows実行機での次作業として分離した。
- [x] ✅ **P2 7月小倉芝の脚質別有利度を距離・馬場状態別に再検証する**
  - 確定値診断へ`--style-breakdown year|distance|track-condition`を追加し、CLI/JSONで内訳を保存可能にした。
  - 小倉芝1200mの好走率差は2022年-21.8pt、2024年-11.6pt、2025年-28.4pt、
    2026年-26.9pt。1800m以上は方向が一貫しなかった。
  - `style-advantage-v3`では「7月・小倉・芝・1200m」だけを`reference`とし、他距離の過剰警告を解除。
  - 馬場状態は対象全件が未登録。RAパーサーの既知制約として別タスクへ分離した。
- [x] ✅ **P2 函館・小倉の夏開催における脚質別展開有利度を複数年で検証する**
  - 7月1〜22日の芝を2022〜2026年で診断し、函館は年ごとに方向が変わる一方、小倉はデータのある
    2022・2024・2025・2026年すべてで確定RPCI×確定脚質の有利群が逆転すると確認した。
  - 係数・PAI・順位は変更せず、7月の小倉芝を`style-advantage-v2`で`reference`とした。
    その後の距離別検証で1200mだけへ限定し、`style-advantage-v3`へ更新した。
  - Webの展開分析カードへ「参考」と根拠を表示し、強い推奨として誤読されないようにした。
- [x] ✅ **P2 芝の脚質別展開有利度が予測時だけ逆転する原因を切り分ける**
  - 予測RPCI/実績RPCI × 予測脚質/確定脚質の4パターンを同一母集団で比較する診断CLIを追加。
  - 2025年後半は予測同士+5.2pt、2026年前半は+4.4ptで、期間全体では逆転せず。
  - 2026年7月は全体-11.9pt。福島は想定RPCIが主因、函館・小倉は確定値同士でも逆転した。
  - 短期・開催場別の標本だけで本番係数は変更せず、過去年の同開催比較を次の検証候補とした。
- [x] ✅ **P2 脚質別展開有利度を実DBで検証可能にする**
  - 通常バックテストへ有利群・不利群の好走率、リフト、好走率差、相関、JSON明細を追加。
  - 確定RPCI・確定脚質だけで係数の方向性を切り分ける`--validate-style-advantage`を追加。
  - 1000レース診断では、芝は有利群26.4%／不利群19.3%、ダートは33.0%／14.0%で方向性は妥当。
  - 予測込み100レースでは芝だけ逆転したため、仮係数は変更せず、芝の想定RPCIまたは脚質予測を
    次の調査対象とした。
- [x] ✅ **P1 DBマイグレーション不足を検出し、正しい復旧手順を表示**
  - `/health`をlivenessとして維持し、`/ready`でDB接続とORM必須テーブル・列を検査する。
  - Webは一覧APIの500発生時だけreadinessを確認し、スキーマ不足なら
    `python -m alembic upgrade head`、DB停止なら接続確認を案内する。
  - 前タスクで追加したRepositoryメソッドをバックテスト用ラッパーにも委譲し、全体mypyを修復。
  - 検証: API非統合482 passed、関連33 passed、PostgreSQL統合1 passed、Web71 passed、
    API Ruff・mypy 62ファイル、api-client/Web typecheck、Web build成功。

- [x] ✅ **P0 成績未取り込み警告と2026-07-19小倉11Rの実データ不整合を修復**
  - 確定出馬表を完全スナップショットとして置換し、結果送信前に必ず同じ出馬表を登録する。
  - 特別登録は確定枠順・結果を上書きせず、JRA外会場・海外行・障害戦を平地の未取り込み監視から除外。
  - `--only-incomplete`と認証付き全対象キーAPIを追加し、旧開催回キーを正規キーへ置換可能にした。
  - 実DB: 未取り込み343件→0件。小倉11Rは18頭、17頭着順反映。小倉1Rは障害へ再分類。
  - 検証: API非統合477 passed、worker204 passed、変更対象Ruff、API変更対象mypy、
    OpenAPIスナップショット、api-client typecheck成功。

- [x] ✅ **P1 同期完了後に今後のレース予想を事前生成**
  - 認証付き`POST /internal/ingest/forecasts/precompute`と`--step forecasts`を追加。
  - 自動同期をentries/results/special-entries/forecastsの順にし、一覧初回表示での全レース計算を回避。
  - 過去レースは後付け予想せず、今日以降・出走前・出走馬ありだけを再生成する。
  - ボードAPIの欠損時フォールバックは残し、事前生成失敗時も閲覧可能性を維持。
  - 検証: API非統合472 passed、worker194 passed、Web68 passed/build、API Ruff、
    変更対象mypy strict、api-client/Web typecheck成功。worker全体Ruff/mypyには既知違反が残る。

- [x] ✅ **P2 予想martのモデル世代選択を生成日時ベースへ変更**
  - Alembic `004`で`predicted_pace`と`pace_fit`へ`generated_at`を追加。
  - 回顧は最新の想定展開、レースボードは最新の想定展開と最新PAI世代内の最上位馬を選択。
  - 同一モデルの再計算でも生成日時を更新し、モデル名の辞書順へ依存しない。
  - 検証: API非統合467 passed、PostgreSQL統合21 passed、Web68 passed、Ruff、
    変更対象mypy strict、api-client/Web typecheck成功。

- [x] ✅ **P1 レース一覧の予想取得N+1を一括APIへ移行**
  - `GET /api/v1/races/board?date=YYYY-MM-DD`で、レース情報と軽量予想を一括返却。
  - 一覧契約は展開ラベル・信頼度・最上位候補に限定し、PCI/RPCI/PAI実数値を非公開。
  - 初回だけ未作成予想を計算し、以後は`predicted_pace`/`pace_fit`を一括読取。成功時の
    リクエスト単位commitを追加し、従来は破棄されていた予想martを永続化。
  - 出走馬・馬番・枠の変更時だけキャッシュを無効化し、結果更新時は答え合わせ用に保持。
  - 検証: API非統合467 passed、契約33 passed、mart統合2 passed、Web68 passed、Ruff、
    api-client/Web typecheck、Web build成功。全体mypyは既知のNumPy型定義問題、import-linter未導入。

- [x] ✅ **P2 成績未取込警告から安全な手動再同期コマンドを提示**
  - DBで最古の未取込日を集計し、標準10日以上の`recommended_sync_days_back`をAPIへ追加。
  - Web警告バナーに`run_mykeibadb_full_sync.ps1 -DaysBack N`のコピーUIを追加。正常時は非表示。
  - APIからWindowsプロセスを直接起動せず、認証・多重実行・配置差のリスクを回避。
  - OpenAPIとapi-client型を再生成。
  - 検証: API非統合464 passed、Repository統合1 passed、Web67 passed、Ruff、変更対象mypy、
    api-client/Web typecheck、Web build成功。

- [x] ✅ **P1 展開コメント生成をゼロコスト既定モードへ変更**
  - `COMMENT_GENERATOR_MODE=rule`を既定とし、APIキーが環境に残っていても外部APIを呼ばない。
  - Geminiは`COMMENT_GENERATOR_MODE=gemini`と`GEMINI_API_KEY`の両方を明示した場合だけ有効化。
  - Gemini指定時のキー欠損・初期化失敗は`comment-v2`へフォールバックする。
  - 公開APIスキーマ・コメント計算・Web表示は変更なし。
  - 検証: API非統合463 passed、関連29 passed、ruff成功、変更対象2ファイルのmypy strict成功。
    全体mypyは既知のNumPy型定義とPython 3.11設定の不整合で解析前に停止。import-linterは未導入。

- [x] ✅ **P2 Gemini既定モデルを3.5 Flashへ移行し、環境変数化**
  - 提供終了した`gemini-2.0-flash`から`gemini-3.5-flash`へ既定モデルを更新。
  - `GEMINI_MODEL`でモデルを上書き可能にし、DIから`GeminiCommentGenerator`へ渡す。
  - Gemini出力を`comment-gemini-v3`へ更新し、`reasons`には実際に使用したモデル名を記録。
  - APIキー未設定・呼出失敗時の`comment-v2`フォールバックは維持。実APIは呼び出していない。
  - 検証: API非統合457 passed、関連23 passed、ruff成功、変更対象3ファイルのmypy strict成功。

- [x] ✅ **P2 枠順未確定時の展開コメント馬番号表示を修正（comment-v2）**
  - `formation-v1`と同じ枠順確定判定をscenario・ルールコメント・Geminiプロンプトへ結線。
  - 共通の`horse_number_label.py`で、未確定時は「登録順 N（馬番未確定）」、確定後だけ
    「N番」と表示する。API公開スキーマは変更していない。
  - 出力変更を追跡するため、ルール版を`comment-v2`、Gemini版を`comment-gemini-v2`へ更新。
  - 検証: API非統合454 passed、関連74 passed、ruff成功、変更対象5ファイルのmypy strict成功。
    import-linterはローカル環境に未導入。全体mypyは既知のNumPy型定義不整合で解析前に停止。

- [x] ✅ **P1 LightGBMモデルのWindows改行破損修正・AbilityWeights実DB採用判断**
  - `.gitattributes`で`apps/api/models/*.txt`をLF固定。LightGBMの`tree_sizes`がCRLF変換で
    壊れ、実モデルを読めなくなる問題を修正した。既存clone向けにローダーでもLFへ自己修復する。
  - モデル読込失敗時のフォールバックを警告ログへ記録し、追跡中の芝・ダートモデルを実際に
    ロード・予測する回帰テストを追加。
  - 実DBを2025年後半212レース、2026年前半97レースに分けて4候補を比較。
    全3指標が両期間で改善する候補はなく、現行重み（0.55/0.30/0.15）を維持する。
  - 検証: API非統合449 passed、LightGBM関連31 passed、ruff、実DBバックテストCLI成功。
    mypyはローカルNumPy型定義とPython 3.11設定の不整合で対象コード解析前に停止。

- [x] ✅ **P2 取り込み監視をデータ完全性へ拡張**（本セッション・OpenAI Codex）
  - 前日以前のレースが `status=entries` のまま残っている件数と代表20件を、
    `GET /api/v1/ingest-status` で返すようにした。
  - Webトップの `IngestStatusBanner` に成績未取込警告と対象レースへのリンクを追加。
    取り込みログが無い環境でも、未取込レースがあれば警告する。
  - API非統合テスト447件、関連SQL統合テスト1件、Webテスト66件、ruff、Web型チェック・本番ビルド成功。
    mypyはローカルNumPy型定義とPython 3.11設定の不整合で依存型解析前に停止（新規コード原因ではない）。

- [x] ✅ **P1 AbilityWeightsの同一期間比較CLI**（本セッション・OpenAI Codex）
  - `backtest_forecast.py --compare-ability-weights`を追加し、現行・近走のみ・近走重視・
    市場支持重視の4候補を同じ対象レースで比較。
  - 1位馬勝率・1位馬好走率・TOP3好走捕捉率と現行差を表示し、`--output`のJSONにも保存。
  - 候補は検証専用で、`DEFAULT_WEIGHTS`は自動更新しない。実DB実行と採用判断は上記タスクで完了。
  - 検証: API unit+contract 444 passed（関連は40 passed）、変更対象Ruff、
    mypy strict 58ファイル成功、CLI `--help`成功。

- [x] ✅ **P1 統合順位予想 Phase 2 完成（grade・確定馬体重・検証指標）**（本セッション・OpenAI Codex）
  - grade: RA `GradeCD[615]` を公式コードから名称へ変換し、mykeibadb→API→`races.grade`へ保存。
    ability-v3はgradeをクラス補正へ優先利用し、欠損時だけrace_class推定へ縮退。
  - 馬体重: SE `BaTaijyu[324:327]` をresults payloadにも追加し、results単独再取込でも既存
    `race_entries.weight`を確定馬体重で更新。体格と能力を直結させる根拠がないため能力加点は見送り。
  - 検証: バックテストへ統合順位の1位馬勝率・1位馬好走率・TOP3好走捕捉率とJSON出力を追加。
  - テスト: API unit+contract 440 passed、ingestion 191 passed、Web 65 passed、API/ingestion変更対象Ruff、
    lint-imports、api-client/web typecheck、Web build成功。mypy strictは既存lgbm unused-ignore 1件のみ。

- [x] ✅ **P0 Claude Code リモート更新の統合と引き継ぎ資料更新**（本セッション・OpenAI Codex）
  - 状況: Codex が `tasks/current.md` の最優先候補（バックテスト結果のJSON保存）に着手し
    `144ebfd feat(backtest): export reports as json` を作成したが、push前にリモートが16コミット進んでいた。
  - 判断: リモート側 `03bc005 feat(backtest): persist backtest reports to JSON via --output` が同じ目的を
    既に実装済みで、後続コミット（統合順位予想Phase2等）も含まれていたため、マージ競合では
    `apps/api/src/pci/application/backtest.py`・`apps/api/scripts/backtest_forecast.py`・
    `apps/api/tests/unit/application/test_backtest.py`・各ドキュメントをリモート版で採用。
    重複実装で新しいClaude Code作業を上書きしないことを優先した。
  - 検証: 競合マーカーなし、API backtest関連の `py_compile` 成功、api-client typecheck成功、
    Web test 65 passed・typecheck/build成功。API/ingestion-workerの全量pytest/ruff/mypyは
    このCodex環境でPython dev toolingが未構築のため再実行不可（Claude Code側の全量結果は
    `docs/HANDOFF.md` に保持）。

- [x] ✅ **P1 統合順位予想: 印→タグUI・順位明確化 ＋ Phase2（人気・本賞金→ability-v2）**（本セッション）
  - UI（ユーザーFB）: `IntegratedRankingView` を刷新。◎○▲△の印を廃止し、総合順位（1位…）を主役に、
    分類は言葉タグ（本命/対抗/穴（妙味）/人気でも注意/能力上位・中位/展開が向く・向きにくい）で表示。
    プレゼン層のみ（ドメイン/スキーマ不変）。
  - Phase2 データ: 人気(TANSHO_NINKIJUN)・獲得本賞金(KAKUTOKU_HONSHOKIN)を永続化。
    ingestion（models/se_parser/jv_spec 予約offset/mykeibadb_client/ingest_api）→ API（ingest schema・
    ResultInput・RaceEntry・use case・ORM・repository・migration 003）→ ability-v2。
  - ability-v2: form0.55＋本賞金(対数正規化)0.30＋人気0.15 を新しさ加重ブレンド。データ無し成分は
    除外し再正規化 → 旧データは form のみ＝v1相当へ安全に縮退。本賞金がクラス係数 best-effort の限界を緩和。
  - **運用（ユーザー作業）**: `alembic upgrade head`（migration 003）＋過去 results の再取込が必要
    （`MANUAL_SYNC_GUIDE §7.5`）。やらなくても壊れない（縮退）。
  - 検証: API 436 passed（+ability-v2 4件・parser round-trip等）、ingestion 185 passed（+2）、
    Web 65 passed・typecheck・build clean、ruff/lint-imports/mypy clean（既存lgbm/tuple-concat debtのみ・新規0）。
  - 後続で馬体重・gradeを追加済み（上記）。残るのは実JV-Dataの人気/賞金オフセット検証。

- [x] ✅ **P1 統合順位予想（能力×展開）Phase1 実装**（本セッション・ユーザー選択のB節要望を再開）
  - 判断: データ範囲=現データのみ / 統合=2軸分類（本命/対抗/穴/危険）（ユーザー選択・`docs/DECISIONS.md` 2026-07-21）。
  - domain: `pace/ability.py`（ability-v1: 出走頭数正規化着順×クラス係数の新しさ加重平均）、
    `pace/integrated_ranking.py`（integrated-v1: 能力相対順位×展開適性の2軸分類・決定的表示順）。
    いずれも純粋・reasons付き・model_version付き。🧪仮係数は `AbilityWeights`（`docs/SPEC.md §9`-16）。
  - 結線: `forecast_use_cases`（近走+過去レースからability構築→統合）, `dto.py`, `schemas.py`,
    OpenAPI再生成（`openapi.json`+`schema.d.ts`）, `api-client/src/index.ts`（型追加）。
  - web: `IntegratedRankingView.tsx`（新規・◎○▲△と能力上位/中位・展開向く/向きにくいを言葉表示、
    実数値は非表示）を `RaceForecastDashboard` の隊列予想の前に配置。
  - 当時の既知の限界: `grade`未永続化のためクラス係数は`race_class`文字列のbest-effortだった。
    本セッションのability-v3でgrade・人気・本賞金・確定馬体重の永続化まで完了済み。
  - 検証: API 432 passed（+新規domain16・contract1）、Web 65 passed、api/web typecheck・build・
    ruff・lint-imports・mypy --strict すべてclean（既存のlgbm 1件は当環境固有・無関係）。

- [x] ✅ **P0 確定成績未反映を解決**（本セッション・§9-15）
  - 診断で「解析は正常（453件解析可・DATA_KUBUN='7'）」→原因は解析より下流と特定。`batch.py`が
    `record_results`失敗をexit 0に握りつぶしていた欠陥を修正し、送信成功/失敗の件数ログを常設。
    ユーザーが最新コードでresultsステップを再実行→全レース送信成功しアプリに反映（解決）。
  - 残: 障害競走の成績が別途未反映（ユーザー保留）。`DaysBack`既定 7→10 済み。

- [x] ✅ **P0 確定成績未反映の切り分け診断ツール＋件数ログ＋日付窓修正**（本セッション2巡目）
  - 契機: DATA_KUBUN修正（`af922a5`）投入後もユーザー環境で確定成績が反映されず、同期ログは
    全ステップexit 0（件数ではない）。「exit 0で0件」だけでは原因層を特定できないと判明。
  - 対応:
    - `batch.py`: `ingest_results`に「SE何行読込／確定成績何行解析／何レース記録」の件数INFOログ、
      「SE行>0だが確定成績0行」なら診断コマンドを促すWARNINGを追加。`ingest_entries`にも件数ログ。
    - `ingestion/diagnose_results.py`(新規): 実DBのSE行を読み、着順/タイム/上り3F列の有無・
      DATA_KUBUN分布・parse_se_result成功数・SEテーブルの実列名一覧を出力。判定セクションで
      (A)mykeibadb未取得 / (B)列名不一致 / (C)バイト配置バグ を切り分ける。個人・馬名系列は既定で伏せる。
    - `run_mykeibadb_full_sync.ps1`: `DaysBack`既定 7→10（月曜実行時に前々週土曜が窓外へ漏れる
      問題を緩和。7/12の欠落はこれで説明可能）。長期バックフィル用に`-DaysBack 21`例を明記。
  - 対象: `apps/ingestion-worker/src/ingestion/batch.py`,
    `apps/ingestion-worker/src/ingestion/diagnose_results.py`(新規),
    `apps/ingestion-worker/tests/test_diagnose_results.py`(新規3件),
    `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
  - 検証: pytest 182 passed（+3）、ruff clean（新規ファイル）、mypy --strict clean（diagnose_results/
    batch.pyとも新規エラーなし。batch.pyの既存4件はingest_masters内・未編集で対象外）。
  - **未解決**: 診断ツールの実行はユーザー環境（Windows+MySQL）でのみ可能。出力を受け取り次第
    (A)/(B)/(C)を確定して次の手を打つ。上記「進行中」に残置。

- [x] 🧪 **P0（未検証・空振り） 確定成績1週間以上未反映の原因調査とDATA_KUBUN修正**（本セッション）
  - 調査: entries/special-entriesは動いているのに確定成績だけが1週間以上反映されないという
    ユーザー報告を受け、`mykeibadb_client._build_se_record()`を確認。着順・タイム・上り3Fは
    無条件にバイト列へ書き込まれる一方、DataKubun（確定判定に使う値）は`DATA_KUBUN`列が
    存在すればその値をそのまま採用し、存在しない場合のみ着順等の有無から推測していた。
    実環境の`DATA_KUBUN`列がJV-Data本来の確定コードを正しく反映していない場合、着順等が
    揃っていても`parse_se_result`が`None`を返し続ける、という一貫した説明がつく。
  - 対応: 着順・タイム・上り3Fが全て揃っていれば`DATA_KUBUN`列の値に関わらず'7'（確定）とする
    よう変更（単調な修正で、揃っていない行を誤って確定扱いにする副作用はない）。
    `apps/ingestion-worker/tests/test_mykeibadb_client.py`に回帰テストを追加。
  - 検証: `apps/ingestion-worker`は3.12専用のためこの環境にpython3.12でvenvを作成し
    `pip install -e ".[dev]"`後に実行。pytest 179 passed（+1）、ruff/mypy（該当ファイルは
    差分前後で0/25エラーのまま=新規エラーなし）clean。
  - **結果（空振り）**: ユーザーが再pull＆再同期したが確定成績は反映されず、この仮説は外れ
    （または原因の一部でしかない）と判明。修正自体は単調で無害なため残置。真因は別（診断ツールで
    切り分け中。上記の2巡目タスク参照）。

---

- [x] ✅ **P0 展開恩恵馬カードが枠順未確定の馬番を確定情報のように表示するバグを修正**（本セッション）
  - ユーザー報告: 枠順確定前のレースなのに展開予想画面の「展開恩恵馬TOP5」等に馬番が出ている。
  - 原因: `formation-v1`（隊列予想）は`frame_no`（枠番）で確定/未確定を判定し未確定時は
    `formation: null`にする設計だったが、同じ画面のPAI系出力`HorseFitOutput`にはそもそも
    `frame_no`が無く、この判定が一切されていなかった。特別登録段階の`horse_no`は
    `ingest_entries()`がUMABAN=0時に割り当てる暫定連番で、公式馬番ではない。
  - 対応: `HorseFitOutput`/`HorseFitSchema`に`frame_no`を追加（`forecast_use_cases.py`で
    `RaceEntry.frame_no`から供給）。web側`lib/pace.ts`に`horseNumberLabel()`を新設し、
    `frame_no>0`なら「馬番 N」、`frame_no=0`なら「登録順 N（馬番未確定）」を表示。
    `RaceForecastDashboard.tsx`・`HorseFitTable.tsx`・`app/page.tsx`の計5箇所を統一。
    PAIスコア自体は枠順確定前でも意味があるため、カードごと非表示にはせずラベルのみ是正。
  - 対象: `application/dto.py`, `application/forecast_use_cases.py`, `presentation/schemas.py`,
    `openapi.json`+`schema.d.ts`(再生成), `apps/web/src/lib/pace.ts`(+テスト2件),
    `apps/web/src/components/RaceForecastDashboard.tsx`, `apps/web/src/components/HorseFitTable.tsx`,
    `apps/web/src/app/page.tsx`, `tests/unit/application/test_forecast_use_cases.py`(+1件),
    `tests/contract/test_races_api.py`(HORSE_KEYS更新)
  - 検証: API 415 passed（+1）、Web 65 passed（+2）、ruff/mypy --strict/lint-imports/
    typecheck/build すべてclean。
  - 後続対応: `scenario.py`を含む自然文コメントの同種問題は2026-07-22の`comment-v2`で解決済み。

- [x] ✅ **P0 自動同期が来週の特別登録を一度も取り込んでいなかったバグを修正**（本セッション）
  - ユーザー報告「月曜なのに土日の結果・来週の特別登録馬が未反映」を受けて
    `run_mykeibadb_full_sync.ps1`（Task Scheduler「PCI_Sync_Mykeibadb」金/土10:00・日18:00が実行）の
    中身を確認。`batch.py --step entries`/`--step results` のみを呼んでおり、`--step special-entries`
    （mykeibadbの`TOKUBETSU_TOROKUBA`系テーブルを読む独立ステップ）を一度も呼んでいなかったと判明。
    `setup_task_scheduler.ps1`自身のdocstringには「日曜18:00は来週の重賞特別登録取り込みも兼ねる」と
    明記されており、実装漏れ（2026-07-11のTask Scheduler自動化切替時に追加し忘れたと推測）と判断。
  - 対応: `run_mykeibadb_full_sync.ps1`に3番目の呼び出し（`-Step special-entries`、同じ過去7日〜
    未来14日の日付窓）を追加。`sync_mykeibadb.bat`・`MANUAL_SYNC_GUIDE.md`（手順・注意書き・
    6.8節トラブルシューティング新設）・`docs/SPEC.md §6`・`docs/DECISIONS.md`を更新。
  - コード上の修正のみでは今週分の取りこぼしは遡って埋まらないため、ユーザーには
    `--step special-entries`の手動実行コマンドを別途案内。
  - 未解決: 「土日の確定成績が反映されていない」側は自動実行の対象内（`--step results`）のはずで、
    「取りこぼし」ではなく「実行自体の失敗/未発火」の可能性が高いが、このクラウド環境からは
    Task Scheduler実行履歴・ログ・MySQL80状態を確認できないため、ユーザー自身の診断が必要
    （`MANUAL_SYNC_GUIDE.md §6.8`に診断手順を用意）。上記「進行中」に残置。

- [x] ✅ **P3 JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化（技術的負債）**（本セッション）
  - 背景: `jv_spec.py`（RA/SE）のオフセットは実データ校正済みだが、JV-Linkが仕様バージョンを
    上げた場合の再検証手順が文書化されていなかった。
  - 調査で判明: UM/KS/CH（`master_parsers.py`）は既に Ver.3.0.0→Ver.4.9 の実データ差分
    （日付フィールド群24byte追加による名前位置シフト）を確認・反映済みという実例が存在した。
    一方RA/SE側は README.md/common.py が「Ver.3.0準拠」と書いたままで、実際にどのバージョンの
    出力を元に校正したかは未確認と判明（独断で確定せず `docs/SPEC.md §9`-8 に記録）。
  - 対応: `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` を新規作成。UM/KS/CHの実例を
    土台に、`dump_records.py`→`verify_layout.py`（アンカー検証→フィールド目視確認）→
    `locate_haron.py`/`locate_corners.py`（新オフセット特定）→`jv_spec.py`更新→テスト更新→
    記録、の手順と安全策（1レースだけでCONFIRMED昇格しない等）を明文化。
    `README.md`・`docs/SPEC.md`（§6, §9-8）から相互参照を追加。
  - コード変更なし（ドキュメントのみ）。実際の再検証はWindows実行機（JV-Link必須）が必要なため、
    ガイドの実施自体は引き続き未着手（`docs/SPEC.md §9`-8に残置）。

- [x] ✅ **P3 旧handoffファイルの整理（技術的負債）**（本セッション）
  - `docs/handoff-claude-code-2026-06-25.md` の内容を精査。全項目が (a) 現構成と食い違う
    誤情報（`domain/services.py`・`infrastructure/repositories.py`は現存しない旧パス、
    「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
    （ローカル起動→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
    同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）と判明。
    「吸収すべき未収録の情報」が残っていなかったため削除（Git履歴には残るため復元可能）。
  - 対応: ファイル削除、`tasks/backlog.md` 更新。他ドキュメントからの参照なし（削除前に確認済み）。

- [x] ✅ **P3 `mypy --strict` 全体化（技術的負債）**（本セッション、ドキュメント訂正のみ）
  - `tasks/backlog.md` C節に着手したところ、既存の「infrastructure/presentationはスタブ未導入で
    多数エラー・環境要因」という長年の記載が**誤りだったと判明**。
    `python -m mypy src/ --strict` を実行（`.mypy_cache`削除後も再現）すると
    **56ファイル全体で0エラー**。原因は素の`mypy`コマンドが`uv tool`等の隔離環境
    （プロジェクト依存関係が入っていない）を指していたこと（前セッションで発見した
    `pytest`の問題と同根）。fastapi/sqlalchemy/pydanticはいずれも`py.typed`同梱で型情報あり。
  - 対応: `CLAUDE.md`, `AGENTS.md`, `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`,
    `apps/api/README.md`, `tasks/backlog.md` の誤記載をすべて訂正。Definition of Doneも
    「domain・applicationのみ0エラー」から「全体で0エラー」へ引き上げ（実態を反映）。
  - コード変更なし。次回以降は `python -m mypy src/ --strict` を標準コマンドとして使うこと。

- [x] ✅ **P1 データ取り込みの鮮度監視（推奨1・「監視・鮮度表示」）**（コミット `2b83d75`）
  - 目的: `ingest_log` は書き込み専用で、自動同期が静かに失敗し続けても気づく手段が無かった。
  - 対応: 新規 `domain/ops/ingest_log.py`（`IngestLogRepository` Protocol +
    純粋関数 `evaluate_freshness()`）。判定は「直近試行の失敗有無」「直近成功からの経過日数
    （暫定閾値 `STALE_AFTER_DAYS=4`）」のみで、Task Schedulerの具体的cronはハードコードしない。
    `GET /api/v1/ingest-status`（公開GET、`/internal/ingest/*`の認証とは別）を新設し、
    web トップに `IngestStatusBanner` を追加（正常時は控えめ、鮮度低下・失敗時のみ目立つ表示、
    失敗一覧は開閉式）。ログが1件も無い環境（開発/fixture等）は「異常」ではなく「監視対象外」
    として扱い誤警告を防ぐ。
  - 対象: `domain/ops/ingest_log.py`(新規), `infrastructure/repositories/ingest_log_repository.py`(新規),
    `application/dto.py`, `application/ingest_status_use_cases.py`(新規), `presentation/schemas.py`,
    `presentation/routers/status.py`(新規), `presentation/dependencies.py`, `presentation/app.py`,
    `packages/api-client`(型+クライアントメソッド追加), `apps/web/src/lib/ingestStatus.ts`(新規),
    `apps/web/src/components/IngestStatusBanner.tsx`(新規), `apps/web/src/app/page.tsx`
  - 検証: API 414 passed（+18: domain 10・application 5・contract 3）、Web 63 passed（+6）、
    ruff/mypy --strict/lint-imports/typecheck/build すべてclean。
  - 未実施（ユーザー環境でのみ確認可能）: `NOTIFY_WEBHOOK_URL` によるWebhook通知が実際に届くかの
    実地確認。このクラウド環境からは検証不可。

- [x] ✅ **P1 脚質別有利度の差が出ない問題を修正（style-advantage-v1）**（コミット `3d3131e`）
  - ユーザー指摘: 展開分析の有利度が 71/76/91/96 のように高止まりし、機能していると言い難い。
  - 原因: web が「その脚質の最大PAI」を有利度として流用（脚質自体の有利さではない）。
  - 対応: domain に `style_advantage.py` を新設し、想定RPCIの中立点（classify_pace と同じ閾値中点:
    芝50/ダート43）からの乖離を 50=互角の対称スコアへ写像。逃げ競合減点あり。reasons/model_version 付き。
    DTO→schema→OpenAPI→api-client→web（`styleAdvantageScores` + 有利/互角/不利の言葉ラベル）まで結線。
  - 対象: `domain/pace/style_advantage.py`(新規), `application/dto.py`, `forecast_use_cases.py`,
    `presentation/schemas.py`, `tests/`(domain 12件+app 1件+contract 1件), `openapi.json`+`schema.d.ts`(再生成),
    `packages/api-client/src/index.ts`, `apps/web/src/lib/pace.ts`(+テスト2件),
    `apps/web/src/components/RaceForecastDashboard.tsx`
  - 検証: API 396 passed（+14）、Web 57 passed（+2）、ruff/mypy --strict/lint-imports/typecheck/build clean。
  - 関連: ユーザー要望②（展開＋絶対能力の統合順位予想）は `tasks/backlog.md` B節に P1 で記録
    （能力指数の定義が必要なため着手時に仕様合意から）。

- [x] ✅ **P2 バックテスト結果の可視化/保存**（コミット `03bc005`）
  - 対象: `apps/api/src/pci/application/backtest.py`（`report_to_dict`等の変換関数を追加）,
    `apps/api/scripts/backtest_forecast.py`（`--output <path>` オプション追加）,
    `apps/api/tests/unit/application/test_backtest.py`（`TestReportToDict` 2件追加）
  - 結果: `--output` 指定時、混合集計＋（`--track-type`未指定なら）track別内訳をJSONに保存。
    既存の `print` 出力は変更なし。DBテーブル化は見送り（推移ダッシュボードが要る段階で再検討、
    `tasks/backlog.md` A節に記録）。
  - 検証: `python -m pytest tests/unit/ tests/contract/ -q` 382 passed（+2）、ruff/mypy/lint-imports
    clean。`_write_output`の実ファイル書き込み・JSON往復読み込みを手動スモークテストで確認
    （スクリプト層はプロジェクト方針上ユニットテスト対象外のため）。

- [x] ✅ **P1 隊列予想の「自在」過多を距離対応の脚質予測で改善**（コミット `2b083ba`）
  - 原因調査: 直近20レース266頭で自在139頭のうち、混在履歴99頭・履歴なし40頭。
  - 明確な従来脚質は維持し、混在型だけを対象距離・過去走距離・近走順で再判定。
  - 先行・差し同数時は、先行歴が今回より短距離中心なら先行、長距離中心なら差しを優先。
  - 実DB: 自在139頭（52.3%）から40頭（15.0%）へ減少。履歴なしは参考表示を維持。
  - 検証: API unit+contract 380 passed、Web 55 passed、mypy/ruff/import-linter/typecheck/build成功。

- [x] ✅ **P1 枠順確定後の隊列予想機能**（コミット `c679e09`）
  - 特別登録の `frame_no=0` を除外し、全馬に実枠番がある場合だけ `formation-v1` を生成。
  - 脚質と近走序盤位置から、先頭・好位・中団・後方の4ゾーンへ配置。各馬に根拠と信頼度ラベルを付与。
  - OpenAPI型を更新し、展開予想画面にJRA枠色を使ったレスポンシブ隊列ビューを追加。
  - 実DB: entries 278件中、枠順確定112件で生成、未確定166件で非生成を確認。
  - 検証: API unit+contract 374 passed、Web 55 passed、mypy/ruff/import-linter/typecheck/build成功。

- [x] ✅ **P1 レース分析画面のモダンUI刷新**（コミット `4d9e5b5`）
  - 共通ヘッダーとデザイントークンを追加し、レース一覧・展開予想・確定後回顧を同じUIへ統一。
  - 一覧は開催日カレンダーをデスクトップのサイドバーへ移し、レースカードの状態・導線を明確化。
  - 予想・回顧はダークヒーロー、要約カード、解説、的中表示を情報優先度に沿って再構成。
  - 回顧画面の表面からPCIという専門用語を外し、数値を増やさずペース傾向として表示。
  - 検証: Web 55 tests / typecheck / production build がすべて成功。実データの一覧・予想・回顧URLがHTTP 200。

- [x] ✅ **P1 想定RPCI 受入基準の判定方針を決める（製品判断）**（`docs/DECISIONS.md` 2026-07-11）
  - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
  - 理由: MAEの未達幅は2回の独立計測で一貫した構造差。UIは実数値非表示のため、製品価値に直結する
    ラベル一致率(33%ランダムを上回る)とPAIリフト(track別1.18〜1.32x)は実効性ありと判断。
  - 見直し条件: `forecast_accuracy` 蓄積増加、またはダートの外れに偏りが見えた場合に再検討。
  - 注記: 受入基準の文言自体（blended/track別のどちらで判定するか）は基準を定めた側の確認が必要な
    別問題として `docs/SPEC.md §9`-3 に残置（この決定の範囲外）。

- [x] ✅ **P2 `backtest_forecast.py` の既定出力に track 別内訳を追加**
  - 対象: `apps/api/src/pci/application/backtest.py`(`group_races_by_track`追加),
    `apps/api/scripts/backtest_forecast.py`(`_print_track_breakdown`追加),
    `apps/api/tests/unit/application/test_backtest.py`(テスト2件追加)
  - 結果: `--track-type` 未指定時、混合集計に加え芝/ダート別内訳も自動表示。再予測はせず、
    既存の `ForecastBacktester.run()` を track 別サブセットで再実行するのみ（application層は
    グルーピングのみ純粋関数化しテスト、DB配線はスクリプト層のまま）。
  - 検証: `python -m pytest tests/unit/ tests/contract/ -q` 364 passed（+2）、ruff/mypy/lint-imports clean。

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

## 次に着手する候補（今スプリントの当面・優先順位順）

（進行中タスクはなし。以下は `tasks/backlog.md` と実DB確認から整理した残タスク。）

- [ ] **P1 直近1年の重複レース450組を安全に統合する**
  - 状態: ⬜設計待ち
  - 完了条件: 正規キーの判定、RaceEntry・予想mart・関連FKの移行、dry-run、件数照合を経て旧キーを削除する。
  - 制約: 自動削除は行わない。正規・旧キーで成績や出走馬が異なる組を先に分類する。

- [ ] **P2 実JV-Dataの人気・賞金予約オフセットを検証する**
  - 状態: ⏸Windows JV-Link実機待ち
  - 対象: `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md`

- [ ] **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・上がり3F妥当範囲・`RuleWeights`・`PaiWeights`・
  `FormationWeights`・`DistanceStyleWeights`・`StyleAdvantageWeights`・`AbilityWeights`）
  - 状態: ⬜未着手
  - 背景: `docs/SPEC.md §9` に記載の仮仕様。実データ検証後に確定する方針（独断で確定しない）。
    `FormationWeights`（脚質70%/近走序盤位置30%・4ゾーン境界）と`DistanceStyleWeights`
    （距離スケール・新しさ減衰・先行距離補正）は2026-07-12にCodexが追加した仮係数
    （`docs/SPEC.md §9`-10, `docs/DECISIONS.md` 2026-07-12参照）。`AbilityWeights`
    （近走内容0.55/本賞金0.30/人気0.15のブレンド比・新しさ減衰・本賞金対数レンジ等）は
    2026-07-21にability-v2として追加（`docs/SPEC.md §9`-16）。
  - 完了条件: 対象定数ごとに実データでの妥当性検証結果を記録し、確定 or 調整の判断を
    `docs/DECISIONS.md` に残す。formation-v1については隊列ゾーン一致率（実際の後方カメラ等の
    確定データがあれば）での再検証が望ましいが、現状データで可能な範囲でよい。`AbilityWeights`は
    migration 003 適用＋過去成績再取込（`MANUAL_SYNC_GUIDE §7.5`）後でないと人気/本賞金データが
    無く検証できない点に注意。
  - ブロック要因: 対象定数ごとの評価指標・受入条件は未確定。独断で正式化しない。

- [ ] **P2 Webhook通知のWindows実地確認**
  - 状態: ⏸通知先設定待ち
  - 完了条件: `NOTIFY_WEBHOOK_URL`を設定し、失敗通知の到達をWindows実行機で確認する。

---

## 保留・ブロック中

- [ ] ⏸ **ダート特徴量追加・学習データ拡張の検討**（`docs/DECISIONS.md` 2026-07-11参照）
  - 状態: ⏸保留（製品判断済み: 現時点では追加投資しない）
  - 見直し条件: `forecast_accuracy` の蓄積データが増える（track毎に100件超など）、
    または実運用でダートの外れ方に偏り（例: 常にハイ側へ外す）が見えた場合に着手を再検討。

- [x] ✅ **P2 統合テスト（testcontainers-postgres）の実行環境整備**
  - CIとローカルDockerで実行可能。今回も重複集計のPostgreSQL統合テスト1件が成功した。
