# HANDOFF — 現在の作業状態

## 2026-08-07 (Claude Code) 作業区切り その7 — 公開後の画面と出力

- 更新日時: 2026-08-07 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `2f79c65 feat: say when the pace suits nearly everyone instead of listing them`
- 作業目的: 公開まで通ったので、**訪問者から見える側**を直す。ドメインの式は変えていない
  （`fit_crowding` の診断を足しただけで、PAI も閾値も pai-v4 のまま）。

### 名称: 利用者向けは PACE LAB

タブ名・API のタイトル・タスク名を **PACE LAB** へ統一した。**指標名（PCI）を名乗りに出さない。**
「PCI を理解していない競馬ファンでも展開予想を活用できること」がコアバリューなので、
理解を前提にした名前を入口に置かない。リポジトリ名・パッケージ名・DB の識別子は
`pci` のままで、変えていない（利用者に見えないため）。

タスクスケジューラは `PaceLab_Sync_Mykeibadb` へ改名した。**旧 `PCI_Sync_Mykeibadb` を
先に削除する**処理を入れてある（両方登録されていると二重に走る）。

### 取り込みスケジュールを JRA の発表時刻から引き直した

根拠: https://jra.jp/faq/pop02/2_2.html

- 出馬表（馬番なし）: 木 16:00 以降
- **馬番付き: 各レース前日の 10:00 から**。JRA 自身が「掲載まで15分程度」と注記している。
  つまり**土曜のレースは金曜、日曜のレースは土曜**に確定する。

実測でも 10:00 ちょうどは特別登録の9件しか返らず、同日 12:03 には36件揃っていた。
10:00 の直後を狙わず、**11:00 と 13:00 の2回**にした（1回目が空振りでも2回目で拾う）。

火21 / 木17 / 金11 / 金13 / 土11 / 土13 / 土21 / 日21 の8回。
`-StartWhenAvailable -WakeToRun -RestartCount 2` などを付け、**沈黙して飛ばされる経路**を塞いだ。
スクリプト冒頭で管理者権限を確認する（以前は全部やってから CIM のエラーで落ちていて、
「管理者で実行しろ」とはどこにも出なかった）。

### 直した不具合

1. **`forecasts/precompute` が Cloud Run の60秒で切られていた**。ワーカー側は300秒許して
   いたので、**待ち側の上限が効かない**。14日分を1リクエストで投げていたのが原因。
   `PRECOMPUTE_CHUNK_DAYS = 1`（開催日1日ずつ）に分け、サービスの `--timeout` も 300s へ。
   長い1本がプール5本のうち1本を占有するため、**無関係なレース一覧まで 504 になっていた**。
2. **`check_ingest_freshness` が失敗の内容を空で出していた**。`error_msg` を読んでいたが
   スキーマ上のフィールドは `error_summary`。`dict.get` は黙って None を返す。
   スクリプトは（stdlib のみで動かすため）モデルを import できないので、
   **ソースから `.get("…")` のキー名を抜いて Pydantic のフィールド集合と突き合わせる**
   テストを足した。
3. **同じ馬が「向く」と「評価を下げたい」の両方に出ていた**（実機で発見）。割引側が
   `fit_label === "不利" || pai < 60` で、合致の下限（PAI 55）と重なっていた。
   pai-v4 で振れ幅を 25 → 10 に縮めたとき、**`60` という数字だけ旧スケールのまま
   取り残されていた**。`fit_label` だけで判定する形にして、構造的に重ならないようにした。

### 公開画面の見直し（P1/P2/P3）

個人ツールだった頃の作りが残っていた。主なもの:

- **運用者向けの情報を訪問者から分離**（`SHOW_OPERATOR_DETAILS=1` のときだけ出す）。
  内部パス・例外文言・再同期の PowerShell が公開画面に出ていた。
  **隠すのは手順であって状態ではない**——遅延そのものは訪問者にも伝え続ける。
- 生の `PAI 62` 表示を全廃。非専門家向けという前提に反するうえ、
  **脚質をまたいだ比較（実測で否定された使い方）を誘う**。
- 語彙を「向く／向きにくい／影響は小さい」へ統一（「合致」は内部用語）。
- **免責フッターを常設**（的中を保証しない・推奨ではない・JRA / JRA-VAN とは無関係）。
- 見出しを「この展開が向きそうな馬」へ。以前は能力の並びを看板にし、前置きで
  「単勝人気の順より当たりません」と断っていた。実測（1位馬の勝率 20.2% 対 36.9%）には
  忠実だったが、**最初に目に入る情報が自己否定**だった。限界は消さず、畳んだ先へ移した。

### 「向く」が多すぎる問題 — 手法A まで実装、**測定待ち**

実機で16頭中15頭が「向く」になった。**原因は構造で、バグではない。**
合致は馬ごとの絶対閾値（PAI >= 55）で、**レース内で何頭該当するかを制御していない**。
想定ペースが強く傾くと脚質ボーナスだけで前に行く馬が丸ごと超える
（振れ幅10 × 逃げ1.0 = 60、先行0.65 = 56.5）。
**展開の恩恵は相対的な価値で、全員に向く流れは誰の武器でもない。**

- 手法A（表示層）を実装。合致が出走馬の半数以上なら見出しを
  「展開では絞りにくいレースです」に替え、頭数を明示して一覧を畳む。
- **`CROWDED_SHARE = 0.5` は暫定値。** 1レースあたりの合致割合の分布を測っていない。
- 測る道具を足した（`summarize_fit_crowding` / `--diagnose-pai` の「レースあたりの合致割合」）。
  既存の `summarize_fit_label_shares` は全頭を混ぜた構成比で、
  **1レース内で何頭合致するかが見えなかった**。

**次の担当へ: 先に測ること。** 「半数以上のレース比率」と「全頭合致の比率」を見て、
合致の段階化（強い合致／合致）をドメインへ入れるか、閾値55の再較正で足りるかを決める。
`docs/DECISIONS.md` の ADR-2026-08-04 により、**レース内相対化（上位N頭だけ合致）は採らない**
（PAI を脚質をまたいで比べることになる）。閾値をUI側へ写経しないこと（80/70・60 の教訓）。

診断は**読み取り専用**（`scripts/backtest_forecast.py` / `application/backtest.py` に
`commit()` / `session.add` / INSERT / UPDATE / DELETE は無い）。`.env` が Supabase を
指したままでも本番データは変わらない。対象は確定済みレースのみ。

### `tasks/current.md` の重複を掃除した

前回までの更新で、新しい節を**過去の日付ブロック全てに**追記していた（同じ節が4か所）。
2026-08-04 の節を読むと 08-07 のタスクが混ざる状態で、引き継ぎ資料として誤読を招く。
古い3か所を削除し、08-07 の作業には独立した `##` ブロックを立てた。

### テスト状況

```
apps/api: 831 passed (tests/unit/ tests/contract/)
apps/web: 186 passed (24 files) / tsc --noEmit 通過
Ruff 0 / mypy --strict 0（66 files）/ lint-imports 2 contracts kept
```

### 次の担当がやること

- [ ] **`--diagnose-pai` を実行して合致割合の分布を出す**（上記）。所有者の Windows 機で。
- [ ] GitHub へ `PUBLIC_API_BASE_URL`（Variables）と `PUBLIC_API_TOKEN`（Secrets）を設定する。
      **未設定の間、毎日の鮮度監視はスキップされる。**
- [ ] `PUBLIC_API_TOKEN` の入れ替え（構築中の会話ログに値が残っている・未実施）。
- [ ] **JRA-VAN の規約確認が未了のまま公開されている。** `BETA_ACCESS_USER` /
      `BETA_ACCESS_PASSWORD` で閉じられる（用意済み・未適用）。
- [ ] 土曜11:00 の実行で**日曜の出馬表**が入ることを確認する（新スケジュールの検証）。

### 再開コマンド

```bash
cd apps/api
python -m pytest tests/unit/ tests/contract/ -q
python -m scripts.backtest_forecast --diagnose-pai --limit 500   # ← 合致割合の分布
python -m scripts.check_ingest_freshness --base-url <公開URL>     # 取り込みの鮮度
```

## 2026-08-06 (Claude Code) 作業区切り その6 — 公開の足回り（Cloud Run + Supabase）

- 更新日時: 2026-08-06 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `1f25369 feat(api): add migration verification and mart version pruning`
- 作業目的: アルゴリズムではなく**公開できる状態にする**こと。ドメインのコードは触っていない。

### 決めたこと

| 項目 | 決定 | 理由 |
|---|---|---|
| API の置き場所 | **Cloud Run**（東京） | 実測103MBに対し512Miで足り、ゼロスケールで無料枠に収まる |
| DB の置き場所 | **Supabase**（東京・無料枠 DB 500MB） | 実測123MBに対し4倍の余裕。東京を無料で選べる |
| デプロイ契機 | **手動実行のみ**（`workflow_dispatch`） | GCP 側が未整備。作業ブランチへの push で本番が変わるのは事故のもと |
| マイグレーション | **自動実行しない** | 複数インスタンス同時起動で競合する。スキーマ変更時は事前に手で流す |

容量の実測（`scripts/db_size.py`）: 全体123MB / race_entries 219,329行 58MB /
horses 411,491行 48MB / races 15,931行。約4.7年分で、コアだけなら年21%増。

### 見つけて直した「黙って壊れる」不具合3件

いずれも**エラーを出さずに劣化する**種類で、繋いでから気付くと原因究明が長引く。

1. **`MODELS_DIR`**（`77c113d` 以前・`aee0370` 系）: モデル置き場をソースからの相対で
   解決していたため、パッケージとして入れた途端に見つからず、**例外も出さずに
   ルールベースへ落ちる**。設定項目へ移し、Dockerfile で `/app/models` を指定。
   CI にフォールバック検出のステップを追加した（落ちたらビルド失敗）。
2. **接続プールの既定値**（`77c113d`）: SQLAlchemy 既定は1プロセス最大15本。
   max-instances=3 なら45本で、無料枠の上限に当たると**新しいインスタンスが
   一切繋げなくなる**。3+2=5本/プロセスへ絞った。併せて `pool_pre_ping`
   （アイドル自動停止で死んだ接続を掴むと**最初の1リクエストだけ失敗する**）と
   `pool_recycle=1800` を入れた。
3. **pg8000 と `sslmode`**（`e08775b`）: マネージドDBが配る接続文字列は
   `?sslmode=require` を含むが、pg8000 はこの引数を受け取れず `TypeError` で
   **最初の接続から失敗する**（psycopg2 なら通るためドライバ依存の罠）。
   URL から外して `ssl_context` へ翻訳するようにした。libpq の意味に合わせている。

### 用意した運用スクリプト（`1f25369`）

- `scripts/verify_migration.py` — 移行元と移行先の行数・レースキー範囲を突き合わせる。
  **`pg_restore` は部分的に成功した状態で終わることがある**ため、移行直後に必ず走らせる。
- `scripts/prune_mart_versions.py` — 古い `model_version` の行を削除する（既定 dry-run）。
  **`predicted_pace` は芝とダートで別世代が同時に現役**なので、「新しいN世代」だけで
  切ると書き込み頻度の低い側を現役のまま消す。ドメインの現行世代を固定で残し、
  さらに `--active-days`（既定7）以内に書かれた世代を残す二重の守りにした。
- `scripts/db_size.py` — 容量と世代別行数。行数は `count(*)` 実測
  （`n_live_tup` は ANALYZE 前だと0で当てにならない）。

### 設定漏れを検出する仕組み（`3469962` 以降）

デプロイの設定漏れは落ちる形では現れない。動いたまま静かに壊れるので、
**原因を名乗らせる**方向で手当てした。

- Web の案内文を原因別に分けた。`API_BASE_URL` 未設定は開発用の 127.0.0.1 へ
  落ち、`API_ACCESS_TOKEN` 不一致は全リクエスト401。旧コードはどちらも
  「APIが起動しているか確認してください」と案内していた。**APIは動いている。**
- `scripts/check_deployment.py` を追加。公開URLへ外から当てて、
  `PUBLIC_API_TOKEN` の効き・CORS の広さ・モデルのフォールバックを検出する。
  問題があれば終了コード1。ローカルの実インスタンスで、保護あり／保護なしの
  両方の応答を確認済み。

### 移行の実績（2026-08-06 実施済み）

Supabase（東京・無料）へ移行を完了した。9テーブル・65万行超が完全一致
（`verify_migration` で確認）。レースキー範囲 2022010506010101〜2026080907020608。

移行中に踏んだ落とし穴。**いずれもエラーが出ない／出ても誤解を招く形だった。**

| 事象 | 実際の原因 |
|---|---|
| `sslmode` で落ちる | alembic が `build_engine` を通っていなかった |
| 何も実行されず正常終了 | `env.py` が `.env` を読まず `alembic.ini` のローカルURLへ落ちていた |
| `UnicodeDecodeError` | `alembic.ini` は locale（cp932）で読まれる。日本語コメント不可 |
| `tenant/user not found` | プーラーのホスト名が `aws-0-` と `aws-1-` で違っていた |

手順面では `--disable-triggers` が不要（`pg_restore` は依存順にデータを流す）で、
代わりに `--exclude-table=alembic_version` が必須（手順1で版を記録済みのため衝突）。
`pg_dump` はホストに無いので `docker compose exec db` で使う。
シーケンス（`ingest_log.id`）は正しく移ることを PostgreSQL 16 で確認済み。

移行後、ローカルAPIを Supabase 向きで起動して画面まで確認した（モデル読み込み・
`/ready`・レースボード・予想検証）。容量は **111MB / 500MB**。ローカルの123MBより
小さいのは、入れ直しで不要領域が整理されたため。

### Cloud Run の公開（2026-08-06 実施済み）

`https://pci-api-906588230297.asia-northeast1.run.app`（asia-northeast1・`pciapp-504713`）

`scripts/check_deployment.py` の6項目すべてが意図どおり。特に**予測モデルが
`lgbm-dirt-v6-pci-v3` で動いている**ことを確認済み（`rule-` ならビルド方法の誤り）。

初回は CD ワークフローではなく、Cloud Shell から手動で出した。IAM 連携の設定量が多く、
コンテナが動くかどうかと切り分けたかったため。

```bash
gcloud run deploy pci-api --source apps/api --region asia-northeast1 \
  --memory 512Mi --cpu 1 --min-instances 0 --max-instances 3 \
  --timeout 60s --allow-unauthenticated --env-vars-file ~/env.yaml
```

**`--source` は必ずリポジトリのルートから実行する。** パスが解決できないと
`Building using Buildpacks` に落ち、Dockerfile が使われない。その場合 `MODELS_DIR` が
設定されず、**例外を出さずルールベースへ落ちる**。冒頭の1行が
`Building using Dockerfile` であることを毎回確認すること。

### web の公開（2026-08-06 実施済み）

`https://pciapp.vercel.app`（Vercel `pci_app` / Hobby）

**Vercel 側で詰まった2点。どちらも「Git連携が動いていない」ようにしか見えなかった。**

1. `vercel.json` の `"env": {"API_BASE_URL": "@api_base_url"}`。`@` は廃止された
   Vercel Secrets の参照で、存在しない秘密情報を要求して**ビルド開始前に弾かれる**。
   デプロイが1件も作られないため原因が見えず、プロジェクトを作り直しても直らない。
   削除済み（`52d315e`）。環境変数はダッシュボードで設定する。
2. **Root Directory は空（リポジトリのルート）にすること。** `apps/web` を指定すると
   `vercel.json` のパスと二重になり（`apps/web/apps/web/.next`）、ビルドが失敗する。
   `npm ci` をワークスペース全体で走らせる必要もある（web は `@pci/api-client` に依存）。

環境変数は Settings → **Environments → Production** 配下（旧UIの位置から移動している）。
`API_BASE_URL` と `API_ACCESS_TOKEN`（API の `PUBLIC_API_TOKEN` と同値）の2つ。

### 取り込みの自動化（2026-08-06 完了・検証済み）

`PaceLab_Sync_Mykeibadb`（火21 / 金10 / 金21 / 土10 / 土21 / 日21）。
手動実行で `LastTaskResult: 0`、公開API側の鮮度も最終成功0日前・失敗0件。
ワーカーの `API_BASE_URL` は Cloud Run 直結で、手元のAPIを経由していない。

設計は `docs/design/ingestion-automation.md`。要点は**「止まったと気付く」**方に
重心を置いたこと。実行だけ自動化すると、沈黙する仕組みが1つ増える。

### 次の担当がやること（コードではなく外部の準備）

コード側は揃っている。以下はコンソール作業のため、このセッションでは実行していない。

1. ~~Supabase でプロジェクト作成~~ **完了**（東京・session プーラー :5432）
2. ~~移行の実行~~ **完了**（上記）
3. ~~GCP 側の準備~~ **手動デプロイで公開済み**（上記）。CD ワークフローを使う場合は
   `deploy-cloudrun.yml` 冒頭の Workload Identity 連携が別途必要。
4. ~~Cloud Run の環境変数~~ **設定済み**（`RATE_LIMIT_TRUSTED_PROXIES=1` を含む）

- [ ] GitHub へ `PUBLIC_API_BASE_URL`（Variables）と `PUBLIC_API_TOKEN`（Secrets）を
  設定する。**設定するまで毎日の鮮度監視はスキップされる**（未設定で失敗させると
  毎日通知が飛び、本当の異常に気付けなくなるため）。
- [ ] `PUBLIC_API_TOKEN` の入れ替え。構築中の会話ログに値が残っているため、
  公開サービスのアクセス制御としては入れ替えておくのが望ましい（未実施）。
  `gcloud run services update pci-api --region asia-northeast1 --update-env-vars PUBLIC_API_TOKEN=...`
  と Vercel の `API_ACCESS_TOKEN` を同時に更新する。

**公開状態になったため、次の2点が新たに効いてくる。**

- **JRA-VAN の規約確認が未了のまま公開されている。** 表示しているのは独自指標で
  生データではないが、`BETA_ACCESS_USER` / `BETA_ACCESS_PASSWORD`（web の共有Basic認証）で
  閉じておくのが安全。規約の判断が付くまでの暫定手段として用意してある。
- **データの鮮度が手動運用に依存している。** 取り込みは Windows 機での手動実行のまま。
  止まると画面は壊れず「古いまま」になり、最も気付かれにくい。

### テスト状況

`python -m pytest tests/unit/ tests/contract/ -q` 816 passed / Ruff 0 / mypy --strict 0 /
lint-imports 通過。

### 再開コマンド

```bash
cd apps/api
python -m pytest tests/unit/ tests/contract/ -q
python -m scripts.db_size                      # 容量の現状
python -m scripts.prune_mart_versions          # 掃除の影響（DBは変更しない）
python -m scripts.check_deployment --base-url http://127.0.0.1:8000  # 設定の確認
```

---

## 2026-08-04 (Claude Code) 作業区切り その5 — PAIを中心合わせ＋実効サイズへ（pai-v4）

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `d64c5f2 feat(api)!: adopt the centered, right-sized pace correction (pai-v3 → pai-v4)`
- 作業目的: pai-v3 の感応度を確定する。→ もっと手前に2つの問題があり、そちらを直した。

### 何が起きていたか（順に読むと経緯が追える）

1. **振れの中心がずれていた。** `neutral_rpci`（全履歴の3分位境界の中点）を中心に
   していたが、予測RPCIの分布はそこへ揃わない。

   | コース | 予測RPCI平均 | 中立値 | 平均ずれ | 感応度1.0の平均加点 |
   |---|---:|---:|---:|---:|
   | 芝 | 50.72 | 51.85 | −0.248 | **−6.2点** |
   | ダート | 46.55 | 46.50 | +0.172 | **+4.3点** |

   逃げは両コースとも最良の脚質（芝1.39x・ダート1.41x）。芝では実力と逆へ、
   ダートでは実力と同じ向きへずれていた。**pai-v2 の「脚質の定数効果をPAIへ
   埋め込む」誤りが、別経路で戻ってきていた。**

2. **これで `pace-off` の芝/ダート符号逆転が全て説明できた。** ダートが「補正あり」を
   好んだのは、たまたま定数シフトの向きが実力と一致していたため。展開適性を
   測れていた証拠ではなかった。

3. **中心を合わせると、振れ幅を変えても結果が動かなくなった。**
   全体相関 swing25 +0.073 / swing10 +0.074 / swing5 +0.074 / swing0 +0.073。差は誤差。

4. 実測の効果量そのものが小さい。脚質別展開有利度の「有利−不利」は 芝+2.8% /
   ダート+6.5% しかなく、±25点は過大だった。

### 決めたこと（利用者判断: A「補正を外す」ではなく B「小さく残す」を採用）

- `pace_center_offset_turf = -1.17` / `pace_center_offset_dirt = +0.47`
- `pace_swing` 25.0 → **10.0**
- ラベル閾値 65/40 → **55/45**（同じ規則を新しい振れ幅へ当てた）
- `MODEL_VERSION` pai-v3 → **pai-v4**

精度上は A（`pace-off`）と同等。順位付けにPAIを使わないと既に決めており、PAIの役割は
説明になっているため、製品の中核（展開解説）を個別馬で語れる形を残した。

**オフセットの求め方**: 平均 deviation を0にする解を二分法で解く（`--diagnose-pai` の
「推奨offset」列）。予測平均を中心へ置くだけでは足りない——deviation は±1で頭打ちに
なるため、分布が非対称だと平均が一致していても平均ずれは0にならない。ダートがまさに
これで、予測平均と中立が0.05しか違わないのに平均ずれ +0.172 だった。

### 併せて直したバグ

**pai-v3 で入れた表示バグ。** `_style_reason` の引数が「減点」から「加点」へ変わったのに
閾値が旧スケールのまま残り、符号を見ずに上限だけで分岐していた。結果
**最も不利な馬にも「持ち味を出しやすい流れです」と表示していた**。向きごとの回帰テスト付きで修正。

**web のPAI実数閾値。** `benefitRecommendation` が `pai >= 80` / `>= 70` で分岐しており、
pai-v4 のスケールでは到達しない。**恩恵馬の役割ラベルが黙って止まるところだった。**
ドメインの `fit_label` で判定するよう変更。閾値のUI側への写経をやめた。

### 追記: ラベルを脚質別に測った結果（`369151b` / `3eebebc`）

**良い結果: 合致 > 中立 が、合致の存在する全8セルで成立した。** 「展開が向く」と
言われた馬は実際に走る。ラベルの主目的は果たしている。

**弱点: 「不利 > 中立」の逆転。** ただし2SEを超えるのは芝の差しだけ
（中立14.2% n=493 対 不利26.8% n=153・差12.6%／2SE 7.8%）。他は誤差内。

**原因は脚質構成ではなかった（私の推測が外れた）。** 脚質を固定しても谷は残る。
真因は `pace_affinity` のフォールバック。過去データが無い馬は脚質由来の固定
プロファイルを使い、50%混合を通ると PAI が狭い範囲に固定される。差し（感応度0）なら:

    PAI = 0.5×50 + 0.5×affinity → {40, 45, 50, 52.5} の4値のみ → 5段階中4段階が中立

**「中立」には判断材料が無い馬が集中し**、そうした馬は実績が浅く実際に走らない。

**`自在` は合致へ構造的に到達できなかった**（芝602頭・ダート157頭とも0頭）。
フォールバックが全レベル一律40で山が無く、上限が48だったため。pai-v3でも到達
不可だったので以前からの欠陥。平均ペースを山にした形を与えて修正した（暫定値）。

### 次にやること（差し替え）

- [x] **「判断材料が少ない」を別情報として出した**（`b4798fd`）。 `PaiResult.low_evidence` を
      DTO・APIスキーマ・OpenAPI・TS型・UI まで通した。「材料薄」を併記し、材料が
      薄い馬は「軸候補」「評価下げ」と断定しない。ラベル閾値は変えていない
      （原因が閾値ではないため）。mart へは持たせていない（再計算可能なため）。
- [ ] 自在のフォールバック（山の位置と高さ）を実データで検証する。
- [ ] オフセットの期間変動を監視する（芝は期間外で +0.42 ずれた。振れ幅10なら
      定数シフト3.8点に収まる範囲）。
- [x] **脚質をまたいだ PAI 順位付けを全廃した**（`fd60398`）。

### デプロイ先: Cloud Run に決定（2026-08-04・`7d7f724`）

東京リージョンがあり、web が SSR である以上経路に乗る「Vercel のリージョン ↔
API のリージョン」を短くできるため。無料枠（月200万リクエスト・18万vCPU秒・
36万GB秒）は永続で、実測 103MB・少人数利用の規模なら収まる見込み。

**`deploy-cloudrun.yml` は手動実行のみ。** GCP 側の準備が済むまで動かせないうえ、
作業ブランチへの push で本番が更新されるのは事故のもと。自動化は準備完了後に判断する。

**残っている準備（コードでは進められない）:**

1. **PostgreSQL の置き場所を決める。** Cloud SQL に無料枠は無いので、東京リージョンの
   マネージド Postgres（Neon / Supabase 等）を併用する想定。**ここが最後の未決定事項。**
2. GCP プロジェクト・Artifact Registry（asia-northeast1・Docker形式）の作成
3. Workload Identity 連携とサービスアカウント（必要な権限はワークフロー冒頭に列挙）
4. リポジトリの Variables / Secrets 設定（同上）
5. Cloud Run 側の環境変数。特に:
   - `RATE_LIMIT_TRUSTED_PROXIES=1` — **未設定だとレート制限が実質「全体で N 回/分」になる**
   - `PUBLIC_API_TOKEN` — 未設定だと `/api/v1/*` が無認証で全公開
   - `DATABASE_URL`
6. スキーマ変更を伴うデプロイの前に `alembic upgrade head` を手動で流す
   （複数インスタンス同時起動時の競合を避けるため自動実行しない）

### デプロイ先の決め方（決定済み。以下は判断の経緯）

**まず「今の運用から移る理由があるか」。** 現在はローカルAPIを Cloudflare Quick Tunnel で
公開している（DECISIONS.md 1364行付近）。移行を強制するのは次のどれか。

- 家のPCを起動し続けるのが困る / 24-7 の可用性が要る
- Quick Tunnel は再起動でURLが変わるため人に配れない（named tunnel で足りる可能性あり）
- JRA-VAN 規約を通して一般公開する

取り込みはどのみち Windows 機が要るので、そのPCは運用から外れない。

**移るなら、決め手はアプリよりDB。** Postgres が状態・費用・移しにくさを持つ。先に
Postgres の置き場所を決め、APIをその隣へ置く。別プロバイダに分けると毎リクエストの
往復が増える（1ページで複数回DBを引く）。

判断軸（効き目の大きい順）:

1. **メモリ — 実測済み。制約にならない。**

   | 指標 | 実測 | 意味 |
   |---|---:|---|
   | `image_size_mb` | 410 | どのPaaSでも問題にならない。プル時間が少し延びる程度 |
   | `peak_rss_mb` | 103 | アプリ生成 + LightGBM 読み込みを同一プロセスで測った値 |
   | `container_idle_mem` | 57MiB | uvicorn 常駐のみ（モデルは初回リクエストで遅延読み込み） |

   512MB 枠に対して十分な余裕がある。**メモリで候補が落ちることはない。**
   なお素朴に 57 + 71 と足すと 128MB になるが、numpy 等の共有分を二重に数えるため
   過大。同一プロセスで測った 103MB が正しい（CI の `docker` ジョブで毎回出る）。
2. **リージョン（東京か）** — web は SSR で、**Vercel の関数が描画のたびにAPIを叩く**。
   効くのは「利用者↔API」ではなく「Vercelのリージョン↔APIのリージョン」。両方東京に
   揃えないと1ページあたり数回分の往復遅延が乗る。
3. **スリープの有無** — 夜間の取り込みはコールドスタートを待つだけで実害小。
   利用者の初回表示が遅くなる方が問題。
4. **アイドル時のコスト**

Windows からの ingest 送信は HTTPS 外向きなのでどこでも通る。判断材料にならない。

**決め打ちを恐れなくてよい。** Dockerfile はPaaS非依存、設定は全部環境変数、コードに
プロバイダ固有のSDKは無い。後から移す費用が低い。

**注意: `MODELS_DIR` を設定しないとモデルを読めず、静かにルールベースへ落ちる。**
CI で「ルールベースへ落ちたら失敗」を検証しているが、デプロイ先の環境変数でも必須。

### CI（解消済み）

- [x] **CI の mypy 失敗を解消した**（`95e4067`）。型検査ジョブを Python 3.11 へ。
- [x] **`ruff format` をツリー全体へ適用した**（`78cceaa`・整形のみ・独立コミット）。

### テスト状況（`95e4067`時点・手元）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 770 passed
.venv/bin/python -m ruff check src/ tests/                  # All checks passed
.venv/bin/python -m ruff format --check src/ tests/         # 128 files already formatted
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
cd ../web && npx tsc --noEmit && npx vitest run             # 164 passed / tsc OK
```
OpenAPI・TS型は再生成済み。統合テスト（Docker必須）は手元で未実行。

## 2026-08-04 (Claude Code) 作業区切り その4 — ペース補正が判別に寄与しているかを疑い始めた

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `cdfea00 fix(api): stop pinning the PAI version string in the integration test`
- 作業目的: pai-v3 の感応度を実測で確定する。

### 結論から: 感応度はまだ確定できていない。もっと手前に疑いがある

**`pace-off`（感応度を全て0＝ペース補正を切る）が全体相関で current を上回った。**

| 候補 | 全体 | 芝 | ダート | 上位帯n(芝) |
|---|---:|---:|---:|---:|
| current | +0.069 | +0.056 | +0.102 | 94 |
| swing-light | +0.071 | +0.063 | +0.097 | **18** |
| swing-heavy | +0.065 | +0.048 | +0.105 | 125 |
| **pace-off** | **+0.073** | **+0.071** | +0.086 | 0 |

- **`swing-light` は棄却した。** 芝の上位帯リフト 2.34x は頭数が 94 → 18 へ減った結果で、
  母数の縮小をリフトの改善と読み違えていた。`上位帯n` を併記して見分けられるようにした。
- **`pace-off` は芝で +0.016（切ると改善）・ダートで −0.016（切ると悪化）と符号が逆。**

### ダートが「補正あり」を好む理由が、展開適性とは限らない

脚質内で見ると、**ペース補正が効く脚質ほど判別できていない**（差が2SE未満は誤差内）。

| コース | 脚質 | 感応度 | 差 | ±2誤差 | 判定 |
|---|---|---:|---:|---:|---|
| 芝 | 先行 | 0.65 | +11.5% | 8.0% | 有意 |
| 芝 | 差し | **0.00** | +7.7% | 6.8% | 有意 |
| 芝 | 逃げ | **1.00** | +4.1% | 9.7% | 誤差内 |
| ダート | 差し | **0.00** | +12.3% | 7.3% | 有意 |
| ダート | 追込 | **0.00** | +9.2% | 6.3% | 有意 |
| ダート | 先行 | 0.65 | +6.4% | 8.7% | 誤差内 |
| ダート | 逃げ | **1.00** | +2.6% | 10.6% | 誤差内 |

逃げは PAI が最も広く振れる（芝 25.2→69.3 の44点）のに、判別は最下位。
感応度0の差し・追込で PAI に幅が出るのは `pace_affinity`（その馬自身の過去の
ペース別実績）由来で、**PAI の半分はこれで決まる**。実際に効いているのはこちら。

**脚質内で効いていないのに脚質をまたいだ相関が上がるなら、補正は脚質どうしを
相対的にずらしている。** これは pai-v2 が preferred RPCI でやっていた「脚質の
定数効果をPAIへ埋め込む」ことを、別経路で再現しているだけの可能性がある。
ダートは逃げ1.41x・追込0.47xと定数効果が大きいので、底上げがそのまま相関に見える。

### そのための測定を追加した（`fee566f`・`--diagnose-pai` に含まれる）

`summarize_pace_centering` が、コース別に予測RPCIの平均・中立値・平均ずれ・
感応度1.0の脚質が受け取る**平均加点**を出す。0でなければ定数シフトが起きている。

既知の分布からの概算では、芝 ずれ+0.19 → **+4.8点**、ダート ずれ+0.25 → **+6.2点**。
予測RPCIの分布が `neutral_rpci`（閾値の中点）より高い側に寄っているため。
実測で確認すること。**確認できたら、ずれの中心を閾値中点ではなく予測分布の実測平均へ
置き直すのが筋。** そうして初めて pace-off との比較が公平になる。

### CI が今セッション中ずっと赤だった（3つの原因）

手元の `tests/unit/ tests/contract/` は通っていたが、CIは別の所で落ちていた。

1. **統合テストの `pai-v2` 直書き（私の見落とし・`cdfea00` で修正済み）**
   `30b4909` の世代上げでここだけ取り残された。`tests/integration/` は
   testcontainers（Docker）が要り、CLAUDE.md の常用コマンドに含まれていない。
   **世代を上げたら `tests/integration/` も確認すること。**
2. **`mypy --strict` が CI で失敗（未修正・私の変更とは無関係）**
   ```
   numpy/__init__.pyi:737: error: Type statement is only supported in Python 3.12 and greater
   ```
   CIは Python 3.12 で走るため numpy 2.5.1 が入るが、`[tool.mypy] python_version = "3.11"`
   なので numpy 側スタブの PEP695 構文を 3.11 として解釈して落ちる。
   手元は Python 3.11 で numpy 2.4.6 が入るため再現しない。
   **候補**: (a) Type/Lint ジョブだけ Python 3.11 で走らせる（`requires-python = ">=3.11"`
   と開発環境に一致・1行）、(b) `numpy<2.5` を固定、(c) 3.11サポートを捨てて
   `python_version`/`requires-python` を 3.12 へ上げる。**仕様判断なので未着手。**
3. **`ruff format --check` は 42ファイルで落ちる（未修正・先行して mypy が落ちるため未到達）**
   このリポジトリは ruff format 済みではない。全体整形は独立した判断なので触っていない。

（`fee566f` で誤って `ruff format src/pci/` を全体に流し22ファイルを巻き込んだため、
`b918138` で差し戻した。診断機能そのものは維持している。）

### テスト状況（`cdfea00`時点・手元）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 741 passed
.venv/bin/python -m ruff check src/ tests/                  # All checks passed
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
```
統合テスト（Docker必須）は手元で未実行。CIの結果で確認すること。

## 2026-08-04 (Claude Code) 作業区切り その3 — PAIをコース相対へ作り直し、評価軸も直した

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `bed4de6 fix(api): judge PAI within each running style, not across styles`
- 作業目的: 「PAIが展開適性ではなく脚質を符号化している」（その2で確定）への対処。

### 何を変えたか

**1. PAI を絶対RPCIからコース相対へ作り直した（`30b4909`・pai-v2 → pai-v3）**

`preferred_*`（脚質ごとの理想RPCIを絶対値で持つ）を廃止し、`sensitivity_*`
（コース平均からの振れに対する感応度）へ置き換えた。

```
deviation = clamp((想定RPCI − neutral_rpci(コース)) / 平均帯の半幅, −1, +1)
PAI = 50 + 感応度(脚質) × pace_swing(25) × deviation − 距離減点 − 馬場減点
```

**50 =「この脚質にとって普段どおりの流れ」。** 絶対的な強さではない。

| 脚質 | 感応度 | 芝ハイ | 芝中立 | 芝スロー | ダート中立 |
|---|---:|---:|---:|---:|---:|
| 逃げ | 1.00 | 25.0 | 50.0 | 75.0 | 50.0 |
| 先行 | 0.65 | 33.8 | 50.0 | 66.2 | 50.0 |
| 自在 | 0.60 | 35.0 | 50.0 | 65.0 | 50.0 |
| 差し | 0.00 | 50.0 | 50.0 | 50.0 | 50.0 |
| 追込 | 0.00 | 50.0 | 50.0 | 50.0 | 50.0 |

感応度は21万頭の実測比（`--pace-style-matrix`・自脚質の平均に対する比）から較正した。
差し・追込を0にしたのは、芝とダートで符号が揃わないため（差し 1.04x 対 0.94x）。
ADR-0010「後方脚質は常に互角」と同じ結論に独立に到達している。

**2. ドメインの docstring にあった逆向きの記述を訂正した（`30b4909`）**

`pci.py` と `rpci_forecast.py` に「スロー → 差し・追込有利」とあったが、実測は逆。
前半が緩めば前の馬は脚を溜められるので残りやすい（芝スロー時 逃げ1.21x / 追込0.98x）。
なお `adaptability.py` の旧 preferred 値（逃げ=55でスロー志向）は**方向としては正しかった**。
壊れていたのは絶対値とコース非対応の部分だけで、コードではなく散文が誤っていた。

**3. 評価軸を脚質内比較へ直した（`bed4de6`）**

pai-v3 の PAI は脚質内の相対量なので、**脚質をまたいだ集計では性能を測れない**。
診断側が pai-v2 のままだったため、構造上ほぼ必ず出る「不一致」を判定として出していた。

- `--diagnose-pai` の「PAI順 対 実績順 → 不一致」判定を削除した。
- 代わりに**脚質を固定した上位1/3対下位1/3の好走率差**を出す。脚質の定数効果が落ちる。
- `pai_spread`（上位/下位のPAI差）を併記した。感応度0の脚質は幅が無いので差は偶然。
- 片側30頭未満の行に `*` を付けた。
- `--compare-pai-weights` に上位帯の頭数を併記した。

### 実測結果（2026-06-01以降・500レース・6,575頭）

指標は改善している。ただし**採否の判断はまだできていない**（下記）。

| | pai-v2 | pai-v3 |
|---|---:|---:|
| 最上位帯リフト | 1.25〜1.34x | **1.63x** |
| PAI×好走 相関 | — | +0.069 |

**「PAI帯 → 好走率」が 40-60 帯で沈む件（0.77x・n=3,233）は仕様どおりで、バグではない。**
感応度0の差し・追込（好走率 0.47〜0.99x と元々走らない脚質）がそこへ積み上がるため。
脚質をまたいだ帯集計である限り単調にはならない。`bed4de6` の脚質内比較で見ること。

### 次にやること: 感応度の確定

`sensitivity_*` と `pace_swing` は**比から目分量で置いた暫定値**。実測では候補間に
決定的な差が出ていない（相関は ±0.007 の範囲）。

```
current       全体 相関 +0.069  上位帯 1.63x
swing-light   全体 相関 +0.071  上位帯 1.83x   芝は 2.34x と大きく跳ねた
swing-heavy   全体 相関 +0.065  上位帯 1.60x
front-only    全体 相関 +0.067  上位帯 1.63x
back-included 全体 相関 +0.066  上位帯 1.63x
```

**swing-light の芝 2.34x をそのまま採ってはいけない。** 振れ幅を狭めると base_pai の
上限が 75 → 65 へ下がり、80-100 帯へ届くのは `pace_affinity` が極端に高い少数だけになる。
頭数が出ていなかったため信用できなかった。`bed4de6` で上位帯nを併記したので、再実行して
**頭数を見てから**判断すること。全頭を使う相関側はほとんど動いていない（+0.056 → +0.063）。

```bash
cd apps/api
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500 --diagnose-pai
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500 --compare-pai-weights
```

判断材料は「脚質内の好走率差」を主、「相関」を従とする。上位帯リフトは頭数次第で跳ねるので単独では使わない。

### 触ってはいけないこと

**UI で馬を PAI 順に並べないこと。** ダートの追込はペースの影響を受けない（PAI 50）が、
絶対的な好走率は 0.47x のまま。同じ誤りをその2で一度入れて撤回している（`5d9e01f`）。
脚質をまたいだ提示が要るときは、検証済みの `style_advantage`（脚質別有利度）を使う。

### テスト状況（`bed4de6`時点）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 729 passed
.venv/bin/python -m ruff check src/ tests/                  # All checks passed
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
cd ../web && npm run test && npm run typecheck              # 153 passed / tsc OK
```
OpenAPI は差分なし（CLI診断のみの変更でAPI契約は不変）。

## 2026-08-04 (Claude Code) 作業区切り その2 — 製品価値を測り、順位予想を看板から外した

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `5d9e01f fix(web): stop surfacing PAI-based horse picks; PAI encodes style, not pace fit`
- 作業目的: 「完成度を上げるには何をすべきか」への回答として、まず製品価値そのものを測った。

### この区切りで分かったこと（順に読むと経緯が追える）

1. **統合順位は市場に大きく負けている**（`1144c6d` で比較を実装）

   | 500レース・カバー率100% | 統合順位 | 単勝人気順 | 差 |
   |---|---:|---:|---:|
   | 1位の勝率 | 20.2% | 36.9% | −16.7% |
   | 1位の好走率 | 47.8% | 65.5% | −17.7% |
   | TOP3捕捉率 | 40.6% | 52.4% | −11.8% |

   芝・ダートで差がほぼ同一のため偶然ではない。`ability-v3` は成分に単勝人気を含むのに人気単独より悪い。

2. **成分を切り分けた**（`5ab94ab`・`--compare-ranking-strategies`）
   - PAIを順位付けへ使うと **2.4ポイント悪化**（20.2% → 22.6%）
   - tierと能力scoreのみは**完全に同一**。tierはスコア順3分位なので構造上同じ順序になる
   - PAIを外しても市場に **14.3ポイント届かない**。能力指数そのものが市場に劣る

3. **順位予想を看板から外した**（`4399d61`）。印（本命/対抗/穴/危険）を非表示、見出しを
   「近走内容による能力の並び（参考）」へ、配置を展開解説より後ろへ。
   「買うべき馬の推奨ではありません」と明示。

4. **PAIは展開適性ではなく脚質を符号化していた**（`bf1cc4e`・`--diagnose-pai`）

   | ダート | PAI平均 | 好走率 | 対ベース |
   |---|---:|---:|---:|
   | 差し | 80.3 | 22.5% | 0.99x |
   | 追込 | 75.9 | 10.6% | **0.47x** |
   | 先行 | 66.6 | 29.4% | 1.30x |
   | 逃げ | 63.6 | 31.8% | **1.41x** |

   `_preferred_rpci` が脚質だけで決まりコース補正を持たないため、分布の異なる芝(52.0)と
   ダート(46.5)で順序が反転する。**最も好走する逃げに低い値、最も走らない追込に高い値**を出す。

5. **自分の変更を撤回した**（`5d9e01f`）。3で入れた検討サマリーの「展開が向く馬（PAI上位3頭）」は、
   ダートでは差し・追込を推してしまう。検証済みの脚質別有利度から「恩恵を受ける脚質」だけを示す形へ変更。

### 追加した診断（すべて本番設定を変えない）

```bash
cd apps/api
# 市場比較は標準レポートへ自動で出る（人気データがあれば）
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500
# 順位の並べ方の切り分け
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500 --compare-ranking-strategies
# PAIが展開適性か脚質かの切り分け
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500 --diagnose-pai
```

### 最優先の未完了タスク: PAI の再設計

**単純に preferred をコース別へ引き直すだけでは不十分。** 実データが示すのは、両コースとも
「逃げ > 先行 > 自在 > 差し > 追込」という**同じ順序**で好走するという事実で、
「脚質ごとに理想ペースがある」というPAIの前提そのものが支持されていない。

- 芝: 1.39x / 1.22x / 1.09x / 0.90x / 0.62x
- ダート: 1.41x / 1.30x / 0.87x / 0.99x / 0.47x

再設計の方向としては「脚質の定数効果」と「ペース依存の変動効果」を分離するのが素直。
素データは `--pace-style-matrix` で得られる。ADR-0010（前付けだけ採点・後方は常に互角）と整合させること。

### 正直に記録しておくべき注意点

**脚質別展開有利度の見かけの価値は割り引いて読む必要がある。** 「有利 1.47x / 不利 1.28x」は
どちらもベースライン23.1%を上回っている。採点対象が前付け脚質に限られているためで、
相当部分は「前付けは元々よく走る」という定数効果に由来する。
**ペース依存の純効果は差の +4.3% 側で見るべき**（芝 +2.8% / ダート +6.5%）。

### 未完了（前回の区切りから継続）

- API を再起動しての実画面確認が未実施。
- ダートの「平均」帯の幅（3.4ポイント）が MAE 2.372 の1.4倍しかなく、判別に構造的上限がある。
- 芝モデルの学習に過学習の兆候（検証誤差が [50] 2.64959 → [100] 2.65502）。

### リリースに向けた未着手項目（本セッションでは触れていない）

- **認証・CORS**: CORS は許可オリジン制（`a811e40`）、レート制限も追加済み（`a7e252d`）。
  **ユーザー単位の認証は未着手**（現状はサーバ間トークンのみ）。
- **デプロイ基盤**: API の Dockerfile を追加済み（`aee0370`・PaaS非依存）。`vercel.json` は既存。
  **CD は未着手**（デプロイ先が未定のため、レジストリへの push 段を入れていない）。
- **取り込みの自動化**: Windows機での手動 PowerShell 実行のまま。
- **法務**: JRA-VAN 規約確認（コードでは解決できないため早めに）。

### テスト状況（`5d9e01f`時点）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 720 passed
.venv/bin/ruff check src/ tests/ scripts/                   # All checks passed
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
cd ../web && npm run test && npm run typecheck              # 153 passed / tsc OK
```

## 2026-08-04 (Claude Code) 作業区切り — レースRPCI式の誤りを修正し、全面移行を完了

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `de7a34c feat(api): adopt turf RPCI v2 and rebase the rule weights on the new distribution`
- 作業目的: 利用者からの「アプリのPCIがJRA公式(TARGET)と合わない」という指摘の原因究明と修正。

### 発端と結論

札幌11R（2026-08-02 芝1800m）で照合したところ、**個馬PCIとPCI3はTARGETと完全一致**
（55.6 / 53.9）、**レースPCIだけが不一致**（当アプリ50.6 / TARGET51.6）だった。
調査の結果、`calculate_rpci_from_lap` に**独立した2つの誤り**があると判明した。

1. **中間区間を捨てる** … 前半3Fと後半3Fだけを仮想1200mへ射影するため1200m超で系統的にずれる
2. **前半3Fを常に600m扱い** … JRAのハロンタイムは距離が200mで割り切れない場合だけ先頭区間が
   端数になる（1300m = 100m + 200m×6）ため、端数距離では前半3Fが実際は500m

実測（全15,332レース・データ整合性は100%で不整合0件）:

| 区分 | 件数 | 平均差 | 絶対差平均 | 区分変化 |
|---|---:|---:|---:|---:|
| 端数なし(600m) | 13,503 | +0.905 | 1.202 | 16.5% |
| 端数あり(500m) | 1,829 | +17.252 | 17.252 | **97.3%** |

端数距離は平均差と絶対差が一致＝誤差の向きが常に同じで、全体の11.9%（8レースに1つ）を
一律ハイ寄りへ誤判定していた。

### 完了した内容

1. **UIから指数の実数値を除去**（`7be7808`）。確定後「算出の根拠」と出走前「予測の根拠」の
   両方から `RPCI=51.8` `想定RPCI=43.2` 等が漏れていた。回帰テスト追加。
2. **同一画面のペース区分の食い違いを修正**（同上）。分析APIがレースラップを渡さず常に
   フォールバック値を再計算しており、保存済み `races.rpci_actual` と割れていた。
3. **RPCI式を修正**（`a09c1a6`）。`calculate_rpci_target`（個馬PCIと同じ式をレース自身へ適用）
   へ置き換え。`formula_version` を pci-v2 → **pci-v3**。
4. **閾値を3分位へ再較正**（同上）。芝 49.7/54.0、ダート 44.8/48.2。中点が実績中央値と一致し、
   脚質別有利度の基準（`neutral_rpci`）のずれも解消した。
5. **全15,332レースの `rpci_actual` を再計算**（`recompute_rpci.py --apply`・12,196件更新）。
6. **両コースのモデルを再学習して採用**（`bdc791e` / `de7a34c`）。
7. **`RuleWeights` の較正値を引き直し**（`de7a34c`）。`turf_base_adjust` +5.0→+2.0、
   `dirt_base_adjust` −9.75→−3.5。旧値は誤ったRPCI式の分布由来だった。
8. **既知課題「芝『平均ペース』再現率0%」を解決**。「構造的問題」ではなく上記の式の誤りと
   狭すぎる帯（2.0ポイント）の複合だった。`rpci_forecast.py` の該当 docstring を差し替え。

### 最終状態（2026-06-01以降 500R）

| | 全体 | ダート204R | 芝296R |
|---|---:|---:|---:|
| MAE | 2.399 | 2.404 | 2.396 |
| バイアス | +0.331 | +0.433 | +0.261 |
| 展開ラベル的中率 | 61.4% | 48.0% | 70.6% |
| 有利−不利の好走率差 | +4.3% | +6.5% | +2.8% |

着手前（芝 MAE 4.823 / 有利−不利 −1.5%）から大きく改善。**両コースとも有利−不利差が
正の値**になり、ADR-0010 で「信号が弱い」と記録した問題が解消方向にある。

本番モデル: `rpci_lgbm_turf_v2.txt`（lgbm-turf-v2-pci-v3）/ `rpci_lgbm_dirt_v6.txt`（lgbm-dirt-v6-pci-v3）。
v5・v4・v1 はロールバック用に保持。

### 未完了・既知の課題

- **PAI帯の非単調性（新規発見・未着手）**: 好走率が 20-40帯 1.16x → 60-80帯 0.84x →
  80-100帯 1.29x とV字になる。芝・ダート共通で、式の修正前から存在した。
  最上位帯のリフトは良好（1.25〜1.34x）だが、中間帯の順序付けが機能していない。
  PAIのスコアリング（`adaptability.py`）の見直しが要る。
- **ダートの判別上限**: 「平均」帯3.4ポイントに対しMAE 2.372で比1.4倍。芝は4.3/2.380=1.8倍で
  再現率70.9%に対しダートは66.7%。帯を広げれば改善余地があるが3分位（等頻度）を崩す。
- **芝の学習に過学習の兆候**: 検証誤差が [50] 2.64959 → [100] 2.65502。early stopping で
  best iteration が保存されるため実害はないが、木の深さ・葉数の調整余地がある。
- **統合順位**: ダートは v5→v6 で 50.6%→46.3% と下がり、芝は v1→v2 で 47.4%→49.1% と上がった。
  偶然の変動の可能性が高いが監視継続。
- **API再起動後の実画面確認が未実施**。

### 仮実装・暫定値・未確定仕様

- 監視のラベル系閾値 `label_accuracy ≥ 0.39` / `high_recall ≥ 0.32` は実測の1.25分の1という
  新設の導出。運用実績を見て見直す余地がある。
- 監視の絶対バイアス上限 1.5 も実測からの導出ではない新設値。
- `RuleWeights.rpci_min/max` (35.0/65.0) はLightGBM側の `DEFAULT_RPCI_CLAMP` (20.0/65.0) と
  独立に持つ。ルールベースは式の出力範囲が異なるため。誤較正の証拠が出るまで据え置く。
- 上限クランプ 65.0 は学習ラベル上限90と不一致だが張り付き0件のため据え置き。
- `calculate_rpci_from_lap` は移行前の値を再現・比較するためだけに残している。新規呼び出し禁止。

### テスト状況（`de7a34c`時点）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 699 passed
.venv/bin/ruff check src/ tests/ scripts/                   # All checks passed
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
cd ../web && npm run test && npm run typecheck              # 149 passed / tsc OK
```

### 再開コマンド

```bash
cd apps/api
# 全体（芝・ダート別内訳も自動表示）
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --limit 500
# 本番モデルの期間外監視（2026-08-04以降）
.venv/bin/python -m scripts.backtest_forecast --monitor-dirt
# 式の乖離を再確認する場合（本番設定は変えない）
.venv/bin/python -m scripts.diagnose_rpci --compare-rpci-formula
```

## 2026-08-04 (Claude Code) 作業区切り — 想定RPCIの安全弁を較正、v5採用はモデルファイル待ち

- 更新日時: 2026-08-04 JST
- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `7875c02 fix(api): lower the RPCI clamp floor to the training label range`
- 作業目的: ダート想定RPCIの系統バイアス+2.5の原因を特定し、再学習候補の採否判断をやり直せる状態にする。

### 完了した内容

1. **クランプ診断を追加**（`2a2acb0`）。`summarize_clamp_impact` / `format_clamp_impact` で、
   予測誤差を「クランプ端に張り付いた群」と「内側の群」へ分けて集計する。
2. **クランプを注入可能化**（`db4d538`）。`--clamp-min` / `--clamp-max` で本番設定を変えずに較正を実測できる。
3. **原因を特定**。ダートのバイアスはモデルではなく安全弁の下限35.0が原因と確定した。
   v5は下限で切られる前の領域ではほぼ無バイアス（内側+0.211）だが、より正しく低い値を
   出そうとするほど下限で切られる頭数が増え（76→113R）、全体バイアスの95%が下限由来だった。
4. **下限を35.0→20.0へ較正**（`7875c02`）。学習ラベル範囲の下端に合わせた。根拠は
   `docs/DECISIONS.md` ADR-2026-08-04。

### 実測値（2026-06-01以降・ダート257R / 芝348R）

| | 旧下限35.0 | 新下限20.0 |
|---|---:|---:|
| v4 MAE / バイアス | 4.457 / +2.479 | 3.719 / +1.653 |
| v5 MAE / バイアス | 3.835 / +2.508 | **2.356 / +0.012** |
| v5 展開ラベル的中率 | 78.6% | 78.6%（v4は71.2%） |
| v5 PAI最上位帯リフト | 1.27x | 1.27x（v4は1.19x） |
| 芝（本番設定） | 上下限とも張り付き0件・影響なし | 同左 |

### 未完了の内容・止まっている箇所

**ダートv5の本番採用**。以下は次の担当での対応が必要:

1. `models/rpci_lgbm_dirt_v5_full.txt` が**リポジトリに存在しない**（ユーザーのWindows機のみ）。
   採用にはこのファイルのコミットが要る。
2. 同ファイルの `.meta.json` に `model_version` が無く、v4と同じ特徴量数(39)のため
   `lgbm-dirt-v4-lap-history` にフォールバックしている。**このまま採用するとmart層へv4と記録される**
   （DoD違反）。再学習は不要で、meta.json へ `"model_version": "lgbm-dirt-v5-lap-history"` を追記すれば足りる。
3. `apps/api/src/pci/application/rpci_monitoring.py` の `RpciMonitoringPolicy` は
   `expected_model_version="lgbm-dirt-v4-lap-history"`、閾値もv4採用時評価由来（MAE≤5.94 / |bias|≤4.62）。
   v5採用時は同時に更新しないと `MODEL_MISMATCH` で監視が止まる。
4. `_DEFAULT_DIRT_MODEL_PATH`（`lgbm_forecaster.py:51`）の切替。

### 判断が必要な論点（独断で確定していない）

ADR-2026-08-02（Codex）は次回採用評価に **2026-08-03以降・100レース以上・実績ハイ/平均/スロー各20R以上** を
予約し、2026-06〜08-02を予備評価済み期間としている。今回の比較は 2026-06-01以降257R で、この予約期間ではない。

一方、その採用条件（絶対バイアスが現行より小さい／MAE・分類的中率・PAI最上位帯リフトを悪化させない）は
**新しい下限では4条件すべてv5が満たす**（バイアス +0.012 < +1.653、MAE 2.356 < 3.719、
的中率 78.6% > 71.2%、リフト 1.27x > 1.19x）。見送りの根拠だった「バイアスが縮まらない」は
測定側の欠陥だったことが判明している。

「予約期間の到達を待つ」か「測定欠陥の判明をもって再評価する」かは**運用方針の判断**であり、
本セッションでは確定していない。ユーザーからは採用指示が出ている。

### 対象ファイル

- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`（下限20.0・clamp注入）
- `apps/api/src/pci/application/backtest.py`（`ClampImpact`・診断）
- `apps/api/scripts/backtest_forecast.py`（`--clamp-min` / `--clamp-max`）
- `apps/api/tests/unit/application/test_backtest.py`
- `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`
- `docs/DECISIONS.md`（ADR-2026-08-04）

### 仮実装・暫定値・未確定仕様

- **上限65.0は据え置き**。芝・ダートとも張り付き0件で拘束の証拠がないため。学習ラベル上限90との
  不一致は残る（監視対象）。
- **芝の下限引き下げは長期未検証**。2026-06以降348Rで非拘束を確認しただけ。
- `RuleWeights.rpci_min`（rule-v4）は変更していない。別推定器の安全弁で誤較正の証拠がないため。
- v4監視ポリシーの閾値は旧下限時代の評価由来で、新下限では緩くなる方向（誤検知はしないが感度は落ちる）。

### 既知の不具合・注意事項

- application層は予測器の実装値を参照できないため、`format_report` はクランプ値を
  明示的に渡された時だけ内訳を出す。CLIは常に実際の値を渡している。
- この診断以前に「バイアスを主指標」として下した再学習候補の採否
  （ADR-2026-08-02 の2件）は、いずれも測定欠陥下の判断であり再評価対象。

### テスト状況（2026-08-04・`7875c02`時点）

```
cd apps/api
.venv/bin/python -m pytest tests/unit/ tests/contract/ -q   # 658 passed
.venv/bin/ruff check src/ tests/ scripts/                   # All checks passed
.venv/bin/python -m mypy src/ --strict                      # 0 errors (65 files)
.venv/bin/lint-imports                                      # 2 kept, 0 broken
```

### 再開コマンド

```bash
cd apps/api
# クランプ内訳は標準レポートへ自動で出る（端に張り付きがある時だけ）
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --track-type ダート --limit 500
# 較正を実測する場合（本番設定は変えない）
.venv/bin/python -m scripts.backtest_forecast --date-from 2026-06-01 --track-type ダート --clamp-min 20
```

## 2026-08-03 17:56 JST (OpenAI Codex → Claude Code) 作業区切り

- 更新日時: 2026-08-03 17:56 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 引き継ぎ準備開始時の最新コミット: `5385ac5 fix(ingestion): isolate synthetic result fields`
- 今回の作業目的: 実JV-Link SEレコードの人気・本賞金位置を安全に検証し、未確認の固定長位置を正式経路へ混入させずに作業を区切る。

### 完了した内容

1. `diagnose_jv_result_offsets.py`でmykeibadb参照値と実JV-Link SEを照合する二段階診断を実装した。
2. `SyntheticResultFieldsProvider`でmykeibadb合成レコードだけに予約拡張位置の解析を許可し、JV-Linkとfixtureの既定値を無効にした。
3. 2026-07-18〜19の50件を実測し、既存予約位置が実JV-Linkに適用できないことを確認した。
4. 差分を自己レビューし、デバッグコード、追跡対象外の生レコード、一時JSONが残っていないことを確認した。
5. ingestion-workerの全テスト、Ruff、strict mypyを再実行した。

### 未完了の内容・作業が止まっている箇所

- 実JV-Link SEの人気・本賞金・確定着順の固定長位置は未確定である。
- `diagnose_jv_result_offsets.py`の参照JSONには血統登録番号がなく、レースキーと馬番だけでは「対応馬の不一致」と「SE配置差」を切り分けられないため、ここで停止している。
- 枠順確定後の18レース再同期、8月8〜9日分の結果同期後の新方式コホート再評価、iOS VoiceOver／Android TalkBackの実機確認は運用日または実機待ちである。

### 次に実施する具体的な手順

1. `apps/ingestion-worker/src/ingestion/diagnose_jv_result_offsets.py`の`_load_references()`、`save_references()`、`load_references()`と照合サンプルへ血統登録番号を追加し、同番号を最優先アンカーにする。
2. `apps/ingestion-worker/tests/test_diagnose_jv_result_offsets.py`へ、血統登録番号一致、番号不一致の除外、旧参照JSONの扱いを検証するテストを追加する。
3. 64bit環境の`--export-references`と32bit環境の`--reference-file`を再実行し、同一馬対応が確認できた場合だけ`apps/ingestion-worker/src/ingestion/parser/jv_spec.py`の確定着順・人気・本賞金位置を更新する。

### 対象ファイル

- `apps/ingestion-worker/src/ingestion/diagnose_jv_result_offsets.py`
- `apps/ingestion-worker/src/ingestion/client/base.py`
- `apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`
- `apps/ingestion-worker/src/ingestion/parser/se_parser.py`
- `apps/ingestion-worker/src/ingestion/parser/jv_spec.py`
- `apps/ingestion-worker/src/ingestion/batch.py`
- `apps/ingestion-worker/tests/test_diagnose_jv_result_offsets.py`
- `apps/ingestion-worker/tests/test_mykeibadb_client.py`

### 仮実装・暫定値・未確定仕様

- 候補採用の支持率80%は診断用の暫定基準であり、JV-Data仕様として確定していない。
- 実測50件は診断時の上限であり、プロダクトロジックの閾値ではない。
- 人気`[372:374]`（14/50）、本賞金`[374:380]`または`[374:382]`（13/50）は低支持候補にすぎず、採用していない。
- mykeibadb合成レコードの予約位置は内部互換用であり、実JV-Linkの仕様とは扱わない。

### 既知の不具合・注意事項

- 現在のレースキー・馬番対応では、既存の確定着順`[334:336]`も0/50だった。血統登録番号による再照合なしに固定長位置を変更してはならない。
- 32bit JV-Link用PythonにはPyMySQLがないため、MySQL参照値の書き出しとCOM診断を一プロセスでは実行できない。
- pytest終了時に`.pytest_cache`への書き込み権限警告（WinError 5）が1件出るが、テスト失敗ではない。
- 正式運用のmykeibadb列分解経路は今回の未確定位置を使用しないため、現行アプリの結果取り込みには影響しない。

### テスト実行コマンドと結果

`apps/ingestion-worker`で実行:

```powershell
$env:PYTHONPATH='src'; C:\Users\yuuta\AppData\Local\Programs\Python\Python312\python.exe -m pytest -q
$env:PYTHONPATH='src'; C:\Users\yuuta\AppData\Local\Programs\Python\Python312\python.exe -m ruff check src tests
$env:PYTHONPATH='src'; C:\Users\yuuta\AppData\Local\Programs\Python\Python312\python.exe -m mypy src --strict --python-version 3.12
```

- pytest: 260 passed、キャッシュ書き込み権限警告1件
- Ruff: All checks passed
- strict mypy: 26 source files、Success: no issues found
- build: ingestion-workerには独立したbuildスクリプトがないため未実行。テスト、型チェック、lintで検証した。

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`の最上段
2. 本セクションと直下の「実JV-Link予約位置の検証と安全な縮退」
3. `apps/ingestion-worker/src/ingestion/diagnose_jv_result_offsets.py`
4. `apps/ingestion-worker/tests/test_diagnose_jv_result_offsets.py`
5. `docs/DECISIONS.md`の実JV-Link固定長位置に関する最新決定

### Claude Codeが最初に実行するコマンド

```powershell
git status --short
git log -1 --oneline
cd apps\ingestion-worker; $env:PYTHONPATH='src'; python -m pytest tests\test_diagnose_jv_result_offsets.py tests\test_mykeibadb_client.py -q
```

## 2026-08-03 (OpenAI Codex → Claude Code) 実JV-Link予約位置の検証と安全な縮退

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `ab37eb9`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: mykeibadb合成専用の人気・本賞金予約位置が、実JV-Linkでも安全か検証する。

### 完了した内容

1. `ingestion.diagnose_jv_result_offsets`を追加し、実SEとmykeibadbをレースキー・馬番で照合した。
2. 64bit MySQLと32bit JV-Link COMを最小一時JSONで橋渡しし、生レコードや馬名を保存しなかった。
3. 2026-07-18〜19の50件で、予約位置は人気1/50、本賞金0/50と確認した。
4. 人気・本賞金の実位置は80%以上支持候補がなく、推測によるオフセット変更を見送った。
5. `SyntheticResultFieldsProvider`を追加し、予約拡張はmykeibadb合成時だけ解析するようにした。
6. 診断一時JSONは実行後に削除した。

### 対象ファイル

- `apps/ingestion-worker/src/ingestion/diagnose_jv_result_offsets.py`
- `apps/ingestion-worker/src/ingestion/client/base.py`
- `apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`
- `apps/ingestion-worker/src/ingestion/parser/se_parser.py`
- `apps/ingestion-worker/src/ingestion/parser/jv_spec.py`
- `apps/ingestion-worker/src/ingestion/batch.py`
- `apps/ingestion-worker/tests/test_diagnose_jv_result_offsets.py`
- `apps/ingestion-worker/tests/test_mykeibadb_client.py`
- `tasks/current.md`, `tasks/backlog.md`, `docs/SPEC.md`, `docs/DECISIONS.md`, `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- 人気・本賞金の実JV-Link位置は未確定。最多候補は人気`[372:374]`14/50、
  本賞金`[374:380]`または`[374:382]`13/50で、採用根拠として不足する。
- 既存の確定着順`[334:336]`も同じ対応で0/50だったため、血統登録番号を追加アンカーにした
  SE全体の再校正が必要。現行の正式運用はmykeibadb列分解データなので影響しない。
- 32bit PythonにはPyMySQLがないため、`--export-references`と`--reference-file`の二段階を使う。

### テスト・実測結果

- worker全テスト: 260 passed（pytestキャッシュ書込警告1件のみ）
- Ruff: passed
- strict mypy: 26 source files、passed
- 実COM診断: 50件照合、予約人気1件、予約本賞金0件、80%以上支持候補なし

### 次に実施する具体的な手順

1. 診断JSONへ血統登録番号を追加し、実SE`[30:40]`との一致率で同一馬対応を検証する。
2. 対応が成立した母集団だけで確定着順・人気・本賞金候補を再集計し、複数レースで一意なら`jv_spec.py`を更新する。
3. 枠順確定後に通常同期を実行し、8月8〜9日の18レースを確定出馬表で再予想する。

## 2026-08-03 (OpenAI Codex → Claude Code) 同期先APIを実行単位で切替

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `30c6cb1`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 8000番を安全に再利用できない場合も、`.env`を変更せず最新版APIへ同期する。

### 完了した内容

1. `run_batch.ps1`へ`-ApiBaseUrl`を追加し、`.env`読込後に明示値を適用した。
2. `run_mykeibadb_full_sync.ps1`へ同オプションを追加し、事前疎通と全5バッチ工程へ転送した。
3. HTTP(S)絶対URLだけを許可し、URL内の認証情報を拒否した。
4. Windows PowerShell 5.1で日本語を解析できるよう、変更した両スクリプトをUTF-8 BOM付きに統一した。
5. 最新APIを8998番へ一時起動し、事前疎通と予想18件の生成を実DBで確認した。

### 対象ファイル

- `apps/ingestion-worker/scripts/run_batch.ps1`
- `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
- `apps/ingestion-worker/tests/test_check_mykeibadb.py`
- `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `tasks/current.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 8998番は一時起動例であり固定の代替ポートではない。既定の`API_BASE_URL`は変更していない。
- `apps/ingestion-worker/.venv`のmypyは環境内の`librt.internal`欠落により解析開始前に失敗した。
  同じPython 3.12のシステム環境ではstrict mypyが成功しており、今回のコード型エラーではない。
- 枠順確定後の18レース再同期と、8月8〜9日確定後の信頼度照合件数確認は未完了。
- VoiceOver／TalkBackの実機読み上げ確認は未完了。

### テスト実行コマンドと結果

- `python -m pytest -q`: 253 passed（pytestキャッシュ書込警告1件のみ）
- `python -m ruff check src tests`: passed
- システムPython 3.12の`python -m mypy src --strict`: passed（25 source files）
- PowerShell構文解析・UTF-8 BOM確認: passed
- `run_mykeibadb_full_sync.ps1 -PreflightOnly -ApiBaseUrl http://127.0.0.1:8998`: passed
- `run_batch.ps1 -Step forecasts -Mode mykeibadb -ApiBaseUrl http://127.0.0.1:8998`: 対象18、生成18、スキップ0

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`の`ApiBaseUrl`解決と全5工程への転送
2. `apps/ingestion-worker/scripts/run_batch.ps1`の`.env`読込後のURL検証・上書き
3. `apps/ingestion-worker/tests/test_check_mykeibadb.py`のAPI上書き回帰テスト

### 次に実施する具体的な手順

1. 枠順確定後、`run_mykeibadb_full_sync.ps1`を通常実行し、18レースの予想を確定出馬表で再生成する。
2. 8月8〜9日の結果確定後にresults同期を行い、`GET /api/v1/forecast-performance?days=180`で芝・ダート件数増加を確認する。
3. iOS VoiceOverとAndroid TalkBackで、予想検証サマリーと詳細タブの読み上げ順を確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) 所有PID不明のAPI待受を安全に検出

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `0e8df93`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: Windowsで待受だけが残る状態を停止中と誤判定せず、安全に復旧案内する。

### 完了した内容

1. `Get-ApiListenerProcess`を、接続とプロセスを返す`Get-ApiListenerState`へ置き換えた。
2. 待受あり・所有プロセスなしを`ORPHANED`、終了コード6として診断する。
3. 通常再起動では2秒待って再照会し、残留時は停止・起動をせず例外で中断する。
4. Uvicorn所有者、別プロセス、停止状態に関する既存の安全判定を維持した。
5. `docs/LOCATION_TEST.md`へ待機・再診断・Windows再起動の復旧手順を追記した。

### 対象ファイル

- `apps/api/scripts/restart_local_api.ps1`
- `docs/LOCATION_TEST.md`
- `tasks/current.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 再照会待ち2秒は、実機で観測した短時間の残留を吸収する暫定的な運用値。
- 入れ子PowerShellで所有者照会を模擬したテストでは、`ORPHANED`分岐へ入り対象プロセスを保護したが、
  外側から観測した終了コードは1へ正規化された。通常の`-File`実行ではコード上の6を返す。
- Windows以外のローカル起動は本スクリプトの対象外。

### テスト実行コマンドと結果

- UTF-8 BOM・PowerShell構文解析: passed
- STOPPED: exit 1、passed
- BLOCKED: 別プロセスを継続したまま検出、passed
- ORPHANED: 所有者照会欠落を模擬し、対象プロセスを継続したまま検出、passed
- READY: 最新API＋実DB＋予想検証API契約、passed

### Claude Codeが最初に確認するファイル

1. `apps/api/scripts/restart_local_api.ps1`の`Get-ApiListenerState`
2. 同スクリプトの`ORPHANED`分岐と再照会ループ
3. `docs/LOCATION_TEST.md`の`ORPHANED`復旧手順

### 次に実施する具体的な手順

1. 実運用cloneを最新コミットへ更新し、`restart_local_api.ps1 -CheckOnly`を通常の8000番で実行する。
2. 枠順確定後の通常同期で、8月8〜9日の18レースを確定出馬表へ更新する。
3. 結果同期後、新方式の芝・ダート照合件数が増えたことを確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) 通常同期と新方式の事前予想生成を再開

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `5cbf12c`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 0件だった新方式の予想について、未来出馬表を同期して事前保存を開始する。

### 完了した内容

1. mykeibadb MySQLの接続を確認し、83テーブルを読めることを確認した。
2. mykeibadb.exeでJV-Link差分を取得し、exit 0を確認した。
3. 2026-07-24〜2026-08-17についてentries、race-metadata、results、special-entriesを順に同期した。
4. 出馬表144レース、確定成績140レースをAPIへ正常送信した。確定成績の失敗は0件だった。
5. 8月8〜9日の特別登録18レースを取り込み、事前予想18件を生成した。
6. 生成直後の新方式照合件数は芝0・ダート0。レース確定後の結果同期で照合対象になる。

### 対象ファイル

- `tasks/current.md`
- `docs/HANDOFF.md`

### 実行した運用対象

- 読み取り元: mykeibadb MySQL
- 書き込み先: PCI App PostgreSQL
- 対象期間: 2026-07-24〜2026-08-17
- 事前予想対象: 2026-08-08〜2026-08-09の18レース

### 仮実装・暫定値・未確定仕様・既知事項

- 特別登録段階の予想を含むため、枠順確定後のentries同期で同じレースを再生成する必要がある。
- 信頼度3区分の再評価は、芝・ダート各100件へ到達するまで実施しない。
- Windowsの8000番に所有PID不在の待受情報が残ったため、今回は最新APIを8998番へ一時起動した。
- APIプロセスとmykeibadb.exeは処理終了後に残っていない。

### 実行結果

- mykeibadb接続診断: passed（83テーブル）
- mykeibadb.exe: exit 0
- entries: RA 144レース、送信成功
- results: 140レース成功、0レース失敗
- special-entries: 18レース登録
- forecasts: 対象18、生成18、スキップ0
- confidence cohort: 芝0、ダート0、目標各100、ready=false

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/forecast_precompute_use_cases.py`の対象条件
2. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`のforecast工程
3. `tasks/current.md`冒頭の結果同期後確認タスク

### 次に実施する具体的な手順

1. 枠順確定後に通常同期を再実行し、18レースの確定出馬表で予想を上書きする。
2. 8月8〜9日の結果確定後にresults同期を実行する。
3. `GET /api/v1/forecast-performance?days=180`で芝・ダート件数が増えたことを確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) ローカルFastAPIの安全な再起動と最新版診断

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `5f06d96`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 旧FastAPIプロセスによる反映漏れを、安全に検出・再起動できるようにする。

### 完了した内容

1. `apps/api/scripts/restart_local_api.ps1`を追加した。
2. 既存Uvicornだけを停止し、別プロセスのポート利用時は`BLOCKED`で中断する。
3. `-CheckOnly`で`STOPPED`、`BLOCKED`、`NOT_READY`、`STALE`、`READY`を診断する。
4. 最新コードを8998番へ一時起動し、実DBでreadinessと新しい予想検証API契約を確認した。
5. 新方式件数は芝0、ダート0、目標各100、`confidence_review_ready=false`だった。
6. `docs/LOCATION_TEST.md`へ通常の再起動・確認コマンドを追加した。

### 対象ファイル

- `apps/api/scripts/restart_local_api.ps1`
- `docs/LOCATION_TEST.md`
- `tasks/current.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- スクリプトはWindows専用。Uvicornのコマンドライン識別に`pci.presentation.app:app`を使用する。
- Bearer認証で予想検証APIを取得できない場合、`-CheckOnly`はreadinessだけを確認し契約確認を省略する。
- 新方式の予想は0件のため、信頼度3区分の精度再評価は実施していない。
- 既存63件は旧方式の履歴であり、新方式の件数へ混在させない。

### テスト実行コマンドと結果

- PowerShell構文解析: passed
- 停止状態診断: `STOPPED` / exit 1を確認
- 別プロセス保護: `BLOCKED` / exit 2、対象プロセスの継続を確認
- 最新API＋実DB診断: `READY` / exit 0を確認
- 最新API＋実DB件数: 芝0、ダート0、目標100、ready=false

### Claude Codeが最初に確認するファイル

1. `apps/api/scripts/restart_local_api.ps1`の`Test-PciApiProcess`
2. 同スクリプトの`-CheckOnly`分岐と`requiredFields`
3. `tasks/current.md`冒頭の新方式予想蓄積タスク

### 次に実施する具体的な手順

1. `apps/api/scripts/restart_local_api.ps1`でFastAPIを最新コードへ再起動する。
2. 通常同期と事前予想生成を実行し、`GET /api/v1/forecast-performance?days=180`の芝・ダート件数を確認する。
3. 両コース各100件到達後、信頼度3区分の母数と一致率を再評価する。

## 2026-08-03 (OpenAI Codex → Claude Code) モバイル予想検証サマリーのフォーカスを可視化

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `aa6c681`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 再評価条件が未達の間に、モバイル検証サマリーのキーボード操作位置を明確にする。

### 完了した内容

1. 稼働中の180日APIを確認し、照合63件、カバー率3.8%であることを再確認した。
2. 稼働中APIは新しい進捗フィールドを返しておらず、最新APIプロセスへの再起動が必要と判定した。
3. モバイルの`summary`へ`focus-visible`時の2px内側リングを追加した。
4. 既存の高さ、余白、短縮表示、読み上げ名は変更していない。

### 対象ファイル

- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 稼働中APIは`confidence_review_target`、`confidence_review_ready`、`confidence_cohort_groups`が欠落した旧プロセス。
- DB内の新方式コース別件数は、最新APIを再起動してから確認する必要がある。
- 高コントラストモード、VoiceOver、TalkBackでの実機確認は未完了。

### テスト実行コマンドと結果

- `npm test --workspace=@pci/web -- ForecastPerformanceSummary.test.tsx`: 5 passed
- `npm run typecheck --workspace=@pci/web`: passed
- `npm test --workspace=@pci/web`: 149 passed
- `npm run build --workspace=@pci/web`: passed

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`のモバイル`summary`クラス
2. `apps/web/src/components/ForecastPerformanceSummary.test.tsx`のフォーカスリング検証
3. `tasks/current.md`冒頭の次候補

### 次に実施する具体的な手順

1. ローカルのFastAPIを最新コミットで再起動し、`GET /api/v1/forecast-performance?days=180`の新3フィールドを確認する。
2. キーボードのTabキーでモバイルサマリーへ移動し、リング、Enter/Spaceでの開閉、状態通知を確認する。
3. 芝・ダート各100件到達後、信頼度3区分の母数と一致率を再評価する。

## 2026-08-03 (OpenAI Codex → Claude Code) モバイル予想検証サマリーの読み上げを明確化

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `d15cbf3`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 390px向け短縮表示を維持しながら、読み上げ機能へ状態・数値・操作を明確に伝える。

### 完了した内容

1. 閉じたモバイルサマリーの`summary`へ、状態に応じた読み上げ名を追加した。
2. 未達時は芝・ダートの現在件数と目標件数、到達時は再評価可能であることを伝える。
3. 展開一致、検証件数、カバー率、詳細を開く操作まで一続きで伝える。
4. 未蓄積状態を含む5つのコンポーネント回帰テストを整備した。
5. 視覚表示の高さ、短縮表記、API契約、デスクトップ表示は変更していない。

### 対象ファイル

- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 読み上げ文言は自動テスト済みだが、VoiceOver／TalkBackでの声・間・開閉状態の通知は実機未確認。
- 視覚上の10px略記と文字拡大時の収まりも、引き続き実機確認が必要。
- `confidence_review_ready=true`到達後の実データ再評価は未完了。

### テスト実行コマンドと結果

- `npm test --workspace=@pci/web -- ForecastPerformanceSummary.test.tsx`: 5 passed
- `npm run typecheck --workspace=@pci/web`: passed
- `npm test --workspace=@pci/web`: 149 passed
- `npm run build --workspace=@pci/web`: passed

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`の`mobileConfidenceLabel`
2. 同ファイルの`mobilePerformanceLabel`と`summary[aria-label]`
3. `apps/web/src/components/ForecastPerformanceSummary.test.tsx`の読み上げ名テスト

### 次に実施する具体的な手順

1. iOS VoiceOverとAndroid TalkBackで閉状態、開状態、詳細タブの順に読み上げを実機確認する。
2. 文字サイズを最大付近へ変更し、390px前後で上段ラベルと右側指標が重ならないことを確認する。
3. `confidence_review_ready=true`到達後、180日APIの信頼度3区分を芝・ダート別に再評価する。

## 2026-08-03 (OpenAI Codex → Claude Code) モバイル予想検証サマリーへ再評価進捗を表示

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `a97a25c`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: スマホで詳細を開かなくても、新しい信頼度指標の再評価時期を判断可能にする。

### 完了した内容

1. `ForecastPerformanceSummary`の閉じたモバイル行へコース別進捗を追加した。
2. 未達時は`新指標 芝X/目標 ダY/目標`、到達時は`新指標 再評価可能`を表示する。
3. 展開一致率、検証件数、カバー率、64px以上の操作領域を維持した。
4. 旧API応答時も既存フォールバックで0/100から表示を継続する。
5. API契約、DB、デスクトップ表示は変更していない。

### 対象ファイル

- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 10pxの略記は390px前後での横収まりを優先した。実機の文字拡大表示は未確認。
- VoiceOver／TalkBack実機確認と、ready到達後の実データ再評価は未完了。

### テスト実行コマンドと結果

- `npm test --workspace=@pci/web -- ForecastPerformanceSummary.test.tsx`: 4 passed
- `npm run typecheck --workspace=@pci/web`: passed
- `npm test --workspace=@pci/web`: 148 passed
- `npm run build --workspace=@pci/web`: passed

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`の`confidenceReviewReady`
2. 同ファイルの`data-mobile-performance-summary`内上段ラベル
3. `apps/web/src/components/ForecastPerformanceSummary.test.tsx`の閉状態・readyテスト

### 次に実施する具体的な手順

1. 実機または390pxブラウザで長い件数表示が見切れないことを確認する。
2. `confidence_review_ready=true`になったら、180日APIで信頼度3区分を再評価する。
3. iOS VoiceOver／Android TalkBackで詳細タブの選択状態と読み上げ順を実機確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) 信頼度指標の再評価到達を自動判定

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `842c256`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 新方式の芝・ダート各100件到達をAPIで一元判定し、再評価の開始時期を見落とさないようにする。

### 完了した内容

1. `GetForecastPerformanceUseCase`へ`_CONFIDENCE_REVIEW_TARGET_PER_TRACK=100`を追加した。
2. `ForecastPerformanceOutput/Schema`へ`confidence_review_target`と`confidence_review_ready`を追加した。
3. 芝・ダート双方が目標以上の場合だけreadyとなる単体テストとAPI契約テストを追加した。
4. Webは未達時に「残り 芝X件・ダートY件」、到達時に「再評価可能」を表示する。
5. 旧API応答では目標100件と取得済み件数から補完し、画面の停止を防ぐ。
6. OpenAPI JSONとapi-client型を再生成した。DBスキーマと保存データは変更していない。

### 対象ファイル

- `apps/api/src/pci/application/dto.py`
- `apps/api/src/pci/application/forecast_performance_use_cases.py`
- `apps/api/src/pci/presentation/schemas.py`
- `apps/api/tests/unit/application/test_forecast_performance_use_cases.py`
- `apps/api/tests/contract/test_status_api.py`
- `packages/api-client/openapi.json`
- `packages/api-client/src/schema.d.ts`
- `apps/web/src/components/ForecastConfidenceCalibration.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 100件は現行の再評価開始条件であり、精度保証の基準ではない。
- 判定は選択した30/90/180日の期間内にある新方式の照合済み予想を対象とする。
- VoiceOver／TalkBack実機確認と、ready到達後の実データ再評価は未完了。

### テスト実行コマンドと結果

- 対象APIテスト: 22 passed（芝100件・ダート99件の未達境界を含む）
- 対象Ruff: passed
- 対象mypy strict: 3 source files、問題なし
- api-client generate / typecheck: passed
- Web: 148 passed
- Web typecheck / production build: passed
- API非統合: 640 passed, 30 deselected
- API Ruff: passed
- API mypy strict: 65 source files、問題なし
- import-linter: 2 contracts kept, 0 broken
- pytestのキャッシュ作成権限に関する警告が1件出たが、テスト結果への影響はない。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/forecast_performance_use_cases.py`の`confidence_review_ready`
2. `apps/web/src/components/ForecastConfidenceCalibration.tsx`の`isReviewReady`
3. `apps/api/tests/unit/application/test_forecast_performance_use_cases.py`の100件到達テスト

### 次に実施する具体的な手順

1. 通常同期と予想事前生成を継続し、予想検証画面の残り件数を確認する。
2. `confidence_review_ready=true`になったら、180日APIの信頼度3区分を芝・ダート別に再評価する。
3. iOS VoiceOver／Android TalkBackで詳細タブの選択状態と読み上げ順を実機確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) 信頼度指標のコース別蓄積進捗を可視化

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `f2f79f9`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 新方式の再評価条件「芝・ダート各100件」への到達状況を、手動SQLなしで確認可能にする。

### 完了した内容

1. `ForecastPerformanceOutput`と`ForecastPerformanceSchema`へ`confidence_cohort_groups`を追加した。
2. `GetForecastPerformanceUseCase`で、新方式のレコードを全体・芝・ダートに集計した。
3. `ForecastConfidenceCalibration`へ芝・ダートの`現在件数/100`を表示した。
   旧APIプロセスで新フィールドが欠けても0/100へフォールバックし、画面を継続表示する。
4. 旧固定0.75はコース別件数へ含めず、全体一致率には残す既存方針を維持した。
5. OpenAPI JSONとapi-clientの`schema.d.ts`を正規生成手順で更新した。
6. DBスキーマと保存済みデータは変更していない。

### 対象ファイル

- `apps/api/src/pci/application/dto.py`
- `apps/api/src/pci/application/forecast_performance_use_cases.py`
- `apps/api/src/pci/presentation/schemas.py`
- `apps/api/tests/unit/application/test_forecast_performance_use_cases.py`
- `apps/api/tests/contract/test_status_api.py`
- `packages/api-client/openapi.json`
- `packages/api-client/src/schema.d.ts`
- `apps/web/src/components/ForecastConfidenceCalibration.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 再評価基準100件は`CONFIDENCE_REVIEW_TARGET`としてWebに保持する。APIは観測値だけを返す。
- 新方式の予想がない期間は芝・ダートとも0/100と表示される。
- VoiceOver／TalkBack実機確認と、各100件到達後の精度再評価は未完了。

### テスト実行コマンドと結果

- 対象APIテスト: 20 passed
- 対象Ruff: passed
- 対象mypy strict: 3 source files、問題なし
- api-client generate / typecheck: passed
- Web: 147 passed（旧API応答の0/100フォールバックを含む）
- Web typecheck / production build: passed
- API非統合: 638 passed, 30 deselected
- API Ruff: passed
- API mypy strict: 65 source files、問題なし
- import-linter: 2 contracts kept, 0 broken
- 初回Webテストはesbuildの作業領域アクセス拒否で起動せず、制限外で同一コマンドを再実行して成功した。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/forecast_performance_use_cases.py`の`confidence_cohort_groups`
2. `apps/web/src/components/ForecastConfidenceCalibration.tsx`の`CONFIDENCE_REVIEW_TARGET`
3. `apps/api/tests/contract/test_status_api.py`の予想検証API契約

### 次に実施する具体的な手順

1. 通常の予想事前生成を継続し、画面の芝・ダート件数を確認する。
2. 両方が100件へ到達したら180日APIで信頼度3区分の母数・一致率を比較し、`docs/DECISIONS.md`へ記録する。
3. iOS VoiceOver／Android TalkBackで詳細タブの選択状態と読み上げ順を実機確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) 信頼度別検証から旧固定値を分離

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `4325b0e`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 新しい読みやすさ指標の検証へ旧固定0.75が混在する状態を、履歴改変なしで解消する。

### 完了した内容

1. `PredictionEvaluationRecord`へ`confidence_method`を追加した。
2. `SqlAlchemyMartRepository.find_prediction_evaluations()`で、保存済み`factors`の
   `classification_margin`から`classification-margin-v1`を識別するようにした。
3. `GetForecastPerformanceUseCase`の全体集計は維持し、`confidence_groups`だけを新方式へ限定した。
4. 旧固定値が全体集計には残り、信頼度別集計から除外される単体テストを追加した。
5. Webの信頼度別欄へ「新しい読みやすさ指標で保存された予想のみを集計」と明示した。
6. DBスキーマ、APIレスポンス形状、保存済み予想は変更していない。

### 対象ファイル

- `apps/api/src/pci/domain/pace/mart_repository.py`
- `apps/api/src/pci/domain/pace/rpci_forecast.py`
- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
- `apps/api/src/pci/infrastructure/repositories/mart_repository.py`
- `apps/api/src/pci/application/forecast_performance_use_cases.py`
- `apps/api/tests/unit/application/test_forecast_performance_use_cases.py`
- `apps/api/tests/integration/test_mart_repository.py`
- `apps/web/src/components/ForecastConfidenceCalibration.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 算出方式は専用DB列ではなく、保存済み根拠コードから識別する。現行1方式では十分だが、
  複数方式を併用する場合は専用列またはAPIの方式別集計が必要になる。
- 新方式の照合済み予想がない期間は、信頼度3区分がすべて「集計なし」と表示される。これは意図した状態。
- VoiceOver／TalkBackの実機確認と、新方式の芝・ダート各100件到達後の再評価は未完了。

### テスト実行コマンドと結果

- `pytest tests/unit/application/test_forecast_performance_use_cases.py -q`: 11 passed
- `pytest tests/integration/test_mart_repository.py -q`: 4 passed
- `pytest -m "not integration" -q`: 638 passed, 30 deselected
- `ruff check src tests`: passed
- `mypy src --strict --python-version 3.12`: 65 source files、問題なし
- `lint-imports`: 2 contracts kept, 0 broken
- `npm test --workspace=@pci/web`: 146 passed
- `npm run typecheck --workspace=@pci/web`: passed
- `npm run build --workspace=@pci/web`: passed
- pytestのキャッシュ作成時に作業領域の権限制限による警告が1件出たが、テスト結果への影響はない。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/infrastructure/repositories/mart_repository.py`の`_confidence_method()`
2. `apps/api/src/pci/application/forecast_performance_use_cases.py`の`confidence_records`
3. `apps/api/tests/unit/application/test_forecast_performance_use_cases.py`の旧方式除外テスト

### 次に実施する具体的な手順

1. 通常の予想事前生成を継続し、`classification_margin`を持つ事前予想を蓄積する。
2. 芝・ダート各100件到達後、180日予想検証APIで信頼度3区分の母数と一致率を確認する。
3. iOS VoiceOver／Android TalkBackで詳細タブの選択状態と読み上げ順を実機確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) LightGBM予想の固定信頼度を解消

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `18b9ab1`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: LightGBM予想の`confidence=0.75`固定により、信頼度別検証が機能しない状態を解消する。

### 完了した内容

1. `lgbm_forecaster._make_forecast()`の固定値0.75を原因として特定した。
2. `_classification_margin_confidence()`を追加し、芝・ダート別の既存展開閾値からの距離を
   0.40〜0.90の表示用読みやすさへ変換した。
3. 分類境界では0.40、平均区分の中央または境界から半帯域以上離れた予測では0.90となる。
4. `classification_margin`理由を追加し、的中確率ではないことをコードと仕様へ明記した。
5. 予測RPCI、展開ラベル、モデルファイル、API契約、保存済み事前予想は変更していない。

### 対象ファイル

- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
- `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`
- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- 0.40〜0.90への線形変換は表示用の暫定指標で、実績に対して校正された的中確率ではない。
- 2026-08-03以前に保存済みの予想は0.75のまま残る。履歴の意味を変えないため遡及更新しない。
- 新旧方式が検証期間内に混在する間は、信頼度区分別集計をモデル固有の校正結果として扱わない。
- 新方式の芝・ダート各100件到達後に、3区分の母数と一致率を再評価する。

### テスト実行コマンドと結果

- `python -m pytest tests/unit/infrastructure/pace/test_lgbm_forecaster.py tests/unit/application/test_forecast_performance_use_cases.py -q`
  - 68 passed
- `python -m pytest -m "not integration" -q`
  - 637 passed, 30 deselected
- `python -m ruff check src tests`
  - passed
- `python -m mypy src --strict --python-version 3.12`
  - 65 source files、問題なし
- `lint-imports`
  - 2 contracts kept, 0 broken
- pytestのキャッシュ作成時に作業領域の権限制限による警告が1件出たが、テスト結果への影響はない。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`の`_classification_margin_confidence()`
2. `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`の`test_confidence_*`
3. `docs/DECISIONS.md`の2026-08-03読みやすさ指標に関する判断

### 次に実施する具体的な手順

1. 通常の予想事前生成を継続し、新方式の`classification_margin`理由を持つ保存済み予想を蓄積する。
2. 芝・ダート各100件到達後、`GET /api/v1/forecast-performance?days=180`で3区分の母数と一致率を比較する。
3. 区分が偏る場合は、的中率に合わせた確率校正ではなく表示境界0.50/0.70の見直しから検討する。

## 2026-08-03 (OpenAI Codex → Claude Code) 事前予想63件の初回不一致傾向レビュー

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `5e9f452`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 条件到達待ちだった事前予想30件の初回レビューを、実DBの保存済み予想だけで実施する。

### 完了した内容

1. `GET /api/v1/forecast-performance?days=180`で63件の照合と39件の一致を確認した。
2. コース別は芝23/38（60.5%）、ダート16/25（64.0%）だった。
3. 不一致APIの24件を方向別に集計した。芝は実際が速め7件・遅め8件、ダートは
   実際が速め6件・遅め3件だった。
4. ダート不一致9件と照合カバー率3.8%では一律補正の根拠として弱いため、係数・閾値・モデルを維持した。
5. DB、コード、モデル、API契約は変更していない。

### 対象ファイル

- `tasks/current.md`
- `docs/SPEC.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- 63件は初回傾向確認の最低条件を満たすが、精度保証の標本ではない。
- 1,640件の評価対象に対し照合済みは63件（3.8%）で、保存済み事前予想の選択偏りが残る。
- 信頼度区分は63件すべて「読みやすい」に属し、区分間比較はまだできない。
- VoiceOver／TalkBackの実機確認と、2026-08-03以降のダートRPCI候補評価は引き続き条件待ち。

### 検証結果

- 180日予想検証API: 63件、39件一致、61.9%
- 芝: 38件、23件一致、60.5%
- ダート: 25件、16件一致、64.0%
- 不一致API: 24件（芝15件、ダート9件）
- 文書のみの変更のため、コードテスト・型チェック・lintは未実行。

### Claude Codeが最初に確認するファイル

1. `docs/DECISIONS.md`の2026-08-03初回レビュー判断
2. `tasks/current.md`先頭の完了記録と次候補
3. `docs/LOCATION_TEST.md`第10節の実機アクセシビリティ確認手順

### 次に実施する具体的な手順

1. 芝・ダート各100件に達するまでは係数を変えず、通常同期と予想事前生成を継続する。
2. 各100件到達後に180日集計と不一致APIを再実行し、方向・信頼度・開催条件別に比較する。
3. iOS VoiceOver／Android TalkBackで詳細タブの選択状態と読み上げ順を実機確認する。

## 2026-08-03 (OpenAI Codex → Claude Code) ダートRPCI監視の3ラベル最低件数を実装

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `c3ecfdf`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 完全未使用期間での次回採用評価条件を、ADRどおり
  「全体100件かつ実績ハイ・平均・スロー各20件」として機械判定する。

### 完了した内容

1. 2026-08-03以降の確定ダートを実DBで監視し、現時点は0件・`no_data`と確認した。
2. `RpciMonitoringPolicy`の最低条件をハイ20件だけから、3ラベル各20件へ変更した。
3. 監視結果へ平均・スロー件数を追加し、CLIとJSONで3ラベルの内訳を確認可能にした。
4. 全体100件・ハイ20件を満たしても平均またはスローが19件なら`accumulating`となる
   回帰テストを追加した。
5. 現行v4モデル、候補モデル、DBデータ、予測値は変更していない。

### 対象ファイル

- `apps/api/src/pci/application/rpci_monitoring.py`
- `apps/api/tests/unit/application/test_rpci_monitoring.py`
- `docs/SPEC.md`
- `tasks/backlog.md`
- `tasks/current.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- 最低件数は`docs/DECISIONS.md`の2026-08-02 ADRで確定済み。新しい暫定値はない。
- 2026-08-03以降の評価対象は現時点で0件のため、候補v6の採否は引き続き保留する。
- VoiceOver／TalkBackの実機確認は未完了。

### テスト・実行結果

- 実DB `backtest_forecast --date-from 2026-08-03 --track-type ダート --monitor-dirt-v4`:
  0件、`no_data`。
- 対象pytest: 13 passed
- API非統合pytest: 630 passed、30 deselected
- API全体Ruff: pass
- API全体mypy strict（Python 3.12）: 65 source files、0 issues
- import-linter: 2 contracts kept、0 broken
- pytestのキャッシュ書き込み警告1件はサンドボックス権限によるもので、結果への影響なし。
- `python -m lint_imports`は環境にモジュールがなく起動できなかったため、同じAPI仮想環境の
  `lint-imports.exe`を直接実行して依存方向を検証した。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/rpci_monitoring.py`の`insufficient_labels`判定
2. `apps/api/tests/unit/application/test_rpci_monitoring.py`
3. `tasks/current.md`先頭の次候補

### 次に実施する具体的な手順

1. 次回同期後に2026-08-03以降を`--monitor-dirt-v4`で確認する。
2. 全体100件・3ラベル各20件のいずれかが未達なら、現行v4を維持して評価を保留する。
3. 条件到達後のみ、同じ完全未使用期間で現行v4と開催月候補v6を比較する。

## 2026-08-03 (OpenAI Codex → Claude Code) ラップ原本・アプリDBの再診断とタスク整理

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `e86828a`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: `tasks/current.md`に残っていた2025年ラップ欠損と2022〜2025年原本確認の
  未完了記録を、実データと実コードに照らして再検証し、引き継ぎ状態を正す。

### 完了した内容

1. `ingestion.diagnose_lap_coverage`を2022-01-01〜2025-12-31に対して実行した。
   mykeibadbの芝・ダート全距離帯でS3/L3保有率100%を確認した。
2. `scripts.diagnose_rpci --by-track-year`を実DBに対して実行した。
   PostgreSQLの2022〜2026年は芝・ダートとも全年でラップ由来100%だった。
3. `rpci_actual`は15,262レース、正常範囲20.0〜90.0の外れ値は0件だった。
4. 2025年の旧形式重複キーに起因した約77レースの欠損は、後続作業ですでに修復済みと再確認した。
   今回は再同期やDB更新を行わず、読み取り専用の診断だけで完了した。
5. `tasks/current.md`内の時系列的に古い未完了項目を完了済みへ訂正した。

### 対象ファイル

- `tasks/current.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- 仮実装・暫定値はない。コード、モデル、DBデータは変更していない。
- VoiceOver／TalkBackの実機確認は未完了。
- 開催月候補v6の再評価は、2026-08-03以降の確定ダートが100レース以上、かつ
  ハイ・平均・スロー各20レース以上になるまで実施しない。

### 診断コマンド・結果

- `python -m ingestion.diagnose_lap_coverage --date 20220101 --date-to 20251231`:
  S3/L3保有率は全8区分で100%、重複行0。
- `python -m scripts.diagnose_rpci --by-track-year`:
  2022〜2026年の芝・ダートでラップ由来100%、`rpci_actual`外れ値0件。
- 文書のみの変更のため、コードテスト・型チェック・lintは未実行。

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`先頭の完了記録と次候補
2. `docs/HANDOFF.md`本セクション
3. `docs/LOCATION_TEST.md`第10節の実機アクセシビリティ確認手順

### 次に実施する具体的な手順

1. iOS VoiceOver／Android TalkBackでモバイル詳細タブの選択状態と読み上げ順を確認し、
   `docs/LOCATION_TEST.md`第10節へ機種・OS・ブラウザ・結果を記録する。
2. 2026-08-03以降の確定ダート件数と3ラベルの各件数を確認し、採用基準に未達なら現行v4を維持する。
3. 基準到達後のみ、完全未使用期間で現行v4と開催月候補v6を同一条件で再評価する。

## 2026-08-03 (OpenAI Codex → Claude Code) 確定成績の部分送信失敗伝播を修正

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `c3e0048`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: `ingest_results()`のAPI送信失敗が`main()`で破棄され、同期がexit 0・
  `status=ok`と誤判定される既知P0不具合を解消する。

### 完了した内容

1. 各日付チャンクの`IngestResultsSummary.sent_ok`／`sent_fail`を`main()`で集計するようにした。
2. レース単位の例外捕捉と後続処理は維持し、全チャンクの処理後に失敗が1件以上あれば
   成功・失敗件数を含むRuntimeErrorを発生させるようにした。
3. 既存のトップレベル例外処理を通じて`ingest_log.status=error`、失敗通知、終了コード1へ伝播する。
   `INGEST_NOTIFICATION_OWNER=wrapper`時は従来どおり`run_batch.ps1`が再試行後に1回だけ通知する。
4. `record_results()`失敗を模擬した`main()`回帰テストを追加し、SystemExit(1)、
   `status=error`、エラー文中の失敗件数を確認した。

### 対象ファイル

- `apps/ingestion-worker/src/ingestion/batch.py`
- `apps/ingestion-worker/tests/test_batch_e2e.py`
- `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`
- `tasks/current.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- 送信失敗があっても同じ実行内の残りレース・日付チャンク・馬場情報処理は継続し、最後に失敗とする。
  部分成功したデータはAPIの既存upsertにより、ラッパー再試行時も安全に再送できる。
- パース不能レコードは従来どおり警告として扱う。本変更の失敗判定はAPI送信・旧キー削除失敗が対象。
- VoiceOver／TalkBack実機確認とダート候補の標本蓄積待ちは引き続き未完了。

### テスト・実行結果

- `pytest tests/test_batch_e2e.py -q`: 53 passed
- `pytest -q`: 251 passed
- `ruff check src tests`: pass
- `mypy src --strict --python-version 3.12`: 25 source files、0 issues
- pytestのキャッシュ書き込み警告1件はサンドボックス権限によるもので、結果への影響なし。

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/src/ingestion/batch.py`の`result_sent_ok`／`result_sent_fail`集計
2. `apps/ingestion-worker/tests/test_batch_e2e.py::TestIngestResults::test_main_exits_nonzero_when_result_delivery_fails`
3. `tasks/current.md`先頭の次候補

### 次に実施する具体的な手順

1. 次回通常同期で`results=0`を確認し、失敗時は`run_batch.ps1`が再試行することをログで確認する。
2. `docs/LOCATION_TEST.md`第10節に従い、iOS VoiceOver／Android TalkBackの実機確認を行う。
3. 2026-08-03以降の確定ダートが100件かつ各展開ラベル20件に達するまで現行v4を維持する。

## 2026-08-03 (OpenAI Codex → Claude Code) 同期プリフライトのWindows実地確認完了

- 更新日時: 2026-08-03 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `46735fb`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 未確認だった`run_mykeibadb_full_sync.ps1 -PreflightOnly`をWindowsで実行し、
  読み取り元MySQL疎通チェックを含む同期開始前検証を完了する。

### 完了した内容

1. Windows実行機の既存`.env`とPython仮想環境を使い、現在の作業ツリーにある
   `run_mykeibadb_full_sync.ps1 -PreflightOnly`を実行した。
2. FastAPI／PostgreSQL readinessと、mykeibadb MySQLの83テーブル確認がexit 0で完了した。
3. `check_mykeibadb.py`の日本語出力だけ文字化けする回帰を発見し、同期ラッパーへ
   `PYTHONIOENCODING=utf-8`、`PYTHONUTF8=1`、PowerShellコンソールのUTF-8設定を追加した。
4. PowerShell 5.1互換のためスクリプト全体をCRLFへ揃え、修正後の実行で日本語表示と
   `Preflight-only check completed.`を確認した。mykeibadb.exeや同期処理は起動していない。
5. 同期ラッパーのUTF-8設定が残ることを`test_check_mykeibadb.py`で回帰テスト化した。

### 対象ファイル

- `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
- `apps/ingestion-worker/tests/test_check_mykeibadb.py`
- `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`
- `tasks/current.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- DB接続設定と秘密値は既存のGit管理外`.env`を利用し、出力・文書・コミットには含めていない。
- ingestion-worker仮想環境のmypyは`librt.internal`欠損で起動不能。コード検証は従来の
  グローバルPython 3.12環境で再実行し、25 source filesで0 issuesを確認した。
- VoiceOver／TalkBack実機確認と、2026-08-03以降のダート候補再評価条件は引き続き未完了。

### テスト・実行結果

- `run_mykeibadb_full_sync.ps1 -PreflightOnly`: exit 0
  - FastAPI／PostgreSQL: ready
  - mykeibadb MySQL: 接続成功、83テーブル
  - 日本語コンソール出力: 修正後は文字化けなし
- `pytest apps/ingestion-worker/tests -q`: 250 passed
- `ruff check apps/ingestion-worker/src apps/ingestion-worker/tests`: pass
- `mypy src --strict --python-version 3.12`: 25 source files、0 issues
- pytestのキャッシュ書き込み警告1件はサンドボックス権限によるもので、テスト結果への影響なし。

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`のUTF-8初期化
2. `apps/ingestion-worker/tests/test_check_mykeibadb.py`のラッパー回帰テスト
3. `tasks/current.md`先頭の次候補

### 次に実施する具体的な手順

1. `docs/LOCATION_TEST.md`第10節に従い、iOS VoiceOverで詳細タブの選択状態と読み上げ順を記録する。
2. Android TalkBackでも同じ遷移を確認し、端末・OS・ブラウザ・読み上げ結果を`tasks/current.md`へ残す。
3. 2026-08-03以降の確定ダートが100件かつ各展開ラベル20件へ達するまでは現行v4を維持する。

## 2026-08-02 (OpenAI Codex → Claude Code) モバイル詳細タブのアクセシビリティ改善完了

- 更新日時: 2026-08-02 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `1e29ba7`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: RPCI候補の次回評価期間を待つ間に、実データを使ってモバイル詳細画面の
  キーボード操作と取り込み警告の視認性を改善する。

### 完了した内容

1. `MobileTabList`を追加し、出走前・確定後の4タブを共通化した。
2. 選択中のタブだけをTabキーの停止位置にし、左右矢印・Home・Endで選択とフォーカスを移動する。
3. `IngestStatusBanner`へモバイル向け状態チップを追加し、復旧操作を44px以上にした。
4. 390px実ブラウザで横はみ出しなし、タブの矢印移動、隊列表示を確認した。
5. 非選択タブ用の空の`hidden`パネルを追加し、すべての`aria-controls`参照先を常時実在させた。
6. `FormationView.headingId`を追加し、モバイル・デスクトップ間の見出しID重複を解消した。
7. 開催日ストリップをナビゲーションランドマーク化し、競馬場タブへ左右矢印・Home・End操作を追加した。
8. 開催日、競馬場、レース行、詳細タブ、隊列内の馬、同一開催レース移動へ明示的な
   `focus-visible`リングを追加し、キーボード操作時の現在位置を視認しやすくした。
9. スマホヘッダーのアイコンだけになる2リンクへ明示的な読み上げ名を付け、操作領域を
   44×44pxへ拡張した。フォーカスリングも主要導線と同じ表示へ統一した。
10. OSの`prefers-reduced-motion`設定が有効な場合、スムーズスクロール、CSS遷移、
    アニメーションを最小化するグローバルスタイルと回帰テストを追加した。
11. 390px幅で表示中テキストのコントラストを監査し、取り込み警告の見出し色を
    `#92400e`、ページ直下と非選択競馬場タブの補助文字を`slate-600`へ変更した。
    白いカード上で基準を満たす`slate-500`は維持し、情報階層を崩さないようにした。
12. 月カレンダーの「他の日程を探す」、前年・前月・翌月・翌年、開催日の操作領域を
    44px以上へ統一した。日付ストリップは既に選択日前4件・後1件へ絞られていたため、
    `tasks/current.md`の古い未完了記録も実コードに合わせて完了へ訂正した。
13. 390px幅のホームと確定後詳細を一括監査し、残っていたヘッダーロゴ、取り込み対象レース、
    検証期間切替、検証詳細の折りたたみ、競馬場タブ、同一開催R移動を44px以上へ拡張した。
14. ホーム・出走前詳細・確定後詳細のARIA参照、ID、操作要素名、見出し順を390px幅で監査した。
    取り込み警告内のラベルを通常テキストへ変更し、モバイル予想検証に非表示`h2`を追加して、
    ページ主見出しより前の見出しと`h1`から`h3`への飛びを解消した。

### 対象ファイル

- `apps/web/src/components/MobileTabList.tsx`
- `apps/web/src/components/MobileTabList.test.tsx`
- `apps/web/src/components/AppHeader.tsx`
- `apps/web/src/components/AppHeader.test.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/app/globals.test.ts`
- `apps/web/src/components/FormationView.tsx`
- `apps/web/src/components/FormationView.test.tsx`
- `apps/web/src/components/RaceDateCalendar.tsx`
- `apps/web/src/components/RaceDateCalendar.test.tsx`
- `apps/web/src/components/MobileRaceGroupedSection.tsx`
- `apps/web/src/components/MobileRaceGroupedSection.test.tsx`
- `apps/web/src/components/MobileRaceNavigation.tsx`
- `apps/web/src/components/MobileRaceNavigation.test.tsx`
- `apps/web/src/components/MobileRaceForecastDashboard.tsx`
- `apps/web/src/components/MobileRaceForecastDashboard.test.tsx`
- `apps/web/src/components/MobilePaceAnalysisDashboard.tsx`
- `apps/web/src/components/MobilePaceAnalysisDashboard.test.tsx`
- `apps/web/src/components/IngestStatusBanner.tsx`
- `apps/web/src/components/IngestRecoveryCommand.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.tsx`
- `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
- `apps/web/src/components/ForecastErrorPattern.tsx`
- `apps/web/src/components/ForecastErrorPattern.test.tsx`
- `apps/web/src/components/ForecastRecentMisses.tsx`
- `apps/web/src/components/ForecastRecentMisses.test.tsx`
- `apps/web/src/lib/ingestStatus.ts`
- `apps/web/src/lib/ingestStatus.test.ts`
- `apps/web/src/app/page.tsx`
- `tasks/current.md`
- `docs/LOCATION_TEST.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- タブは選択時に即時表示する自動アクティベーション方式。API契約や内部PCI/RPCI表示は変更していない。
- 非選択パネルは空の`hidden`要素だけをDOMへ残し、内容は選択時だけ描画する。
- VoiceOver/TalkBackによる実機読み上げは未実施。`tasks/current.md`の実機確認へ残している。
- PCブラウザの静的監査では主要3画面の重複ID、壊れたARIA参照、名前のない表示中操作要素は0件。
  スクリーンリーダー固有の読み上げ文言とスワイプ順は実機で確認する必要がある。
- ダートRPCI候補は2026-08-03以降の最低標本数到達まで評価保留で、既定v4を維持する。

### テスト・実行結果

- `npm.cmd test --workspace=@pci/web`: 24 files / 146 tests passed
- `npm.cmd run typecheck --workspace=@pci/web`: 成功
- `npm.cmd run build --workspace=@pci/web`: 成功
- 型チェックとbuildを同時実行した初回だけ、buildが`.next/types`を更新中に型チェックが参照して
  `TS6053`となった。build→型チェックの順次再実行では両方成功しており、コード起因の失敗ではない。
- Webワークスペースに`lint`スクリプトは未定義。Next.js buildもlintをスキップする既存設定。
- 390px実ブラウザ: `innerWidth=390`、文書幅375、横はみ出しなし。矢印キーで
  `mobile-tab-summary`から`mobile-tab-formation`へフォーカス・選択が同期。
- 隊列表示後も全4タブの参照先が存在し、表示パネルは1件、重複IDは0件。
- ホーム390px実ブラウザ: 開催日ナビゲーションを認識。競馬場タブは札幌から新潟へ
  矢印キーで移動し、`tabIndex`・`aria-selected`・レース一覧が同期。横はみ出しなし。
- 390px実ブラウザ: 競馬場タブと詳細タブで緑色2pxの内側フォーカスリングを実測。
  詳細タブはサマリーから隊列へ移動後も選択状態と表示内容が同期し、文書幅375pxで横はみ出しなし。
- 390px実ブラウザ: ヘッダーの「予想検証」「レース一覧」がアクセシブル名付きリンクとして認識され、
  両方とも44×44px。キーボードフォーカスリングを確認し、文書幅375pxで横はみ出しなし。
- 本番ビルドの圧縮CSSに`@media (prefers-reduced-motion:reduce)`、`scroll-behavior:auto`、
  アニメーション・遷移時間の最小化が保持されることを確認した。
- ホーム390px実ブラウザで、表示領域内の直接テキストノードを対象に前景色と最寄りの
  単色背景を監査した。警告見出し、一覧補助文字、競馬場タブを修正後、4.5:1未満の検出は0件。
- ホーム390px実ブラウザで月カレンダーを開き、「閉じる」は72×44px、年月移動4件と
  開催日は44×44px、`innerWidth=390`・文書幅375pxで横はみ出しなしと確認した。
- ホームと札幌11R確定後詳細を390px実ブラウザで再監査し、表示中のリンク・ボタン・タブ・
  `summary`に44px未満の操作対象は0件。両画面とも`innerWidth=390`・文書幅375px。
- ホーム・中京12R出走前詳細・札幌11R確定後詳細を390px実ブラウザで構造監査し、
  重複ID0件、壊れた`aria-controls`/`aria-labelledby`/`aria-describedby`参照0件、
  名前のない表示中操作要素0件。ホームの表示中見出しは`h1 → h2 → h3`で階層飛びなし。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobileTabList.tsx`の`handleKeyDown`
2. `apps/web/src/components/IngestStatusBanner.tsx`の`data-mobile-ingest-summary`
3. `tasks/current.md`先頭と「スマホ画面向け改善の残タスク」

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
```

### 次に実施する具体的な手順

1. `docs/LOCATION_TEST.md`第10節に従い、iOS VoiceOverで開催日・競馬場・詳細タブの読み上げ順を記録する。
2. 同じ手順をAndroid TalkBackで実施し、選択状態と表示内容の読み上げが同期するか確認する。
3. RPCIは2026-08-03以降の確定ダートが100レースかつ各ラベル20件に達するまで再評価しない。

## 2026-08-02 (OpenAI Codex → Claude Code) 新規29レースの予備評価完了

- 更新日時: 2026-08-02 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `ffd70a0`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 開催月候補を、従来の226レースとは別の未使用期間で予備評価する。

### 完了した内容

1. 2026-07-24以降の確定ダート29レース・365頭を抽出した。
2. 現行v4はMAE 3.283、バイアス +2.014、分類的中率62.1%、PAI最上位帯1.14x。
3. 開催月候補v6はMAE 3.003、バイアス +2.045、分類的中率69.0%、PAI最上位帯1.24x。
4. MAE・分類・PAIの改善方向は再現したが、一次指標のバイアスは改善せず、母数も29件のため
   本番昇格を見送った。既定モデルは`rpci_lgbm_dirt_v4.txt`のまま。
5. 2026-07-24〜2026-08-02は評価済みとして扱い、2026-08-03以降を次の完全未使用期間に予約した。

### 変更ファイル

- `tasks/current.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・未確定仕様・既知事項

- モデル・API・Webのコード変更はない。Windows実行機の候補モデルも変更していない。
- 29レースの結果は方向確認だけで、採用根拠にはしない。
- 次回判定の最低条件は100レースかつ3ラベル各20レース。到達時期は未確定。
- 展開有利度の有利−不利差は両モデルとも負値（v4 -5.1%、候補 -5.7%）で、
  小標本とはいえ別途継続監視が必要。

### テスト・実行結果

- 現行v4バックテスト: 29レース、スキップ0、正常終了。
- 開催月候補v6バックテスト: 29レース、スキップ0、正常終了。
- コード変更がないためpytest・型チェック・lintは前コミット`ffd70a0`の結果を維持する。

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`先頭の新規29レース予備評価
2. `docs/DECISIONS.md`末尾の評価期間予約
3. `apps/api/scripts/backtest_forecast.py`の`--date-from`・`--date-to`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m scripts.backtest_forecast --date-from 2026-08-03 --track-type ダート --limit 300
```

### 次に実施する具体的な手順

1. 2026-08-03以降の対象が100レース未満、またはいずれかの実績ラベルが20件未満なら採否を保留する。
2. 条件到達後、現行v4と`models/rpci_lgbm_dirt_v6_month.txt`を同一期間で比較する。
3. バイアスが縮小し、MAE・分類・PAIが現行を悪化させない場合だけ、新ADRで昇格を検討する。

## 2026-08-02 (OpenAI Codex → Claude Code) ダートRPCI開催月特徴量の独立評価完了

- 更新日時: 2026-08-02 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `c7dc415`
- 作業完了コミット: 本セクションを含むコミット
- 今回の目的: 現行v4を維持したままダート固有特徴量を分離実装し、期間外バイアスへの効果を評価する。

### 完了した内容

1. 実DB診断で、ダートの月別平均RPCIが`35.7〜44.3`、馬場状態別が`41.7〜42.6`と確認した。
2. `feature-set=v5`を追加し、v4へ開催月one-hot 12列を加えた。推論時は
   `ForecastRaceUseCase`が`race.race_date.month`を`RaceContext.race_month`へ渡す。
3. 2026-06-01より前の7,431レースで`lgbm-dirt-v6-month`を学習した。
   学習内テストはMAE 2.345、RMSE 3.017、バイアス -0.576。
4. 2026-06-01以降の同一226レースで評価した。MAE 3.896、バイアス +2.574、
   展開ラベル的中率77.4%、PAI最上位帯リフト1.24x、有利−不利差+2.0%。
5. 本番採用を見送った。現行v4比でMAE・分類は改善したが、一次指標のバイアスが
   `+2.571→+2.574`で改善しなかった。既定モデルと既定パスは変更していない。

### 対象ファイル

- `apps/api/scripts/train_rpci_lgbm.py`
- `apps/api/src/pci/domain/pace/rpci_forecast.py`
- `apps/api/src/pci/application/forecast_use_cases.py`
- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
- `apps/api/tests/unit/test_train_rpci_lgbm.py`
- `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`
- `tasks/current.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- v5は候補作成用の特徴量スキーマであり、本番モデルではない。
- Windows実行機には比較用の`models/rpci_lgbm_dirt_v6_month.txt`と来歴JSONが残るが、Git管理外。
- 開催月の効果には開催場構成の季節変化も含まれ得る。月×競馬場の交互作用は未実装。
- 同じ226レースを複数候補の判断に使っているため、次の採用判断は新しい独立期間を推奨する。
- 期間外バイアス`+2.571`は未解決。既定`rpci_lgbm_dirt_v4.txt`を維持する。

### テスト・検証結果

- `pytest -m 'not integration' -q`: 628 passed、30 deselected
- `ruff check src tests scripts`: pass
- `mypy src --strict --python-version 3.12`: 0 issues（65 files）
- `lint-imports`: グローバルPython・API仮想環境とも`No module named lint_imports`で実行不能
- 実DB学習: 7,431レース、成功。
- 独立バックテスト: 226レース、スキップ0。
- pytestの警告1件はサンドボックスで`.pytest_cache`を作れないことによるもので、結果への影響なし。

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`先頭の開催月特徴量評価
2. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`の`FEATURE_NAMES_V5`
3. `docs/DECISIONS.md`末尾のADR-2026-08-02（開催月特徴量）

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/unit/test_train_rpci_lgbm.py tests/unit/infrastructure/pace/test_lgbm_forecaster.py -q
```

### 次に実施する具体的な手順

1. 次候補へ進む場合は、`train_rpci_lgbm.py`の`feature-set=v5`を上書きせずv6として分離する。
2. 月×競馬場を候補にする前に、競馬場・月セルの最低件数を診断し、疎なセルをまとめる規則を決める。
3. 採用判断には2026-06-01以降226レースだけでなく、新たに蓄積した未使用期間を追加する。

## 2026-08-02 (OpenAI Codex → Claude Code) ダートRPCI再学習評価完了

- 更新日時: 2026-08-02 11:00 JST
- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `1248dd4`
- 作業完了コミット: 本セクション、`tasks/current.md`、`docs/DECISIONS.md`を含むコミット
- 今回の目的: ラップ由来へ統一したデータでダートRPCI候補を再学習し、現行v4と同条件で採用判断する。

### 完了した内容

1. **学習データの残存不整合を解消した。**
   - 初回`v5_full`来歴は旧フォールバック式0.3%混在だった。
   - mykeibadbは2022-01-01〜2026-05-31のS3/L3を100%保持していた。
   - アプリDBでは2025-06-28〜2025-07-20にS3/L3欠損76件があり、すべて旧形式の重複キーだった。
   - 4週末（各70レース、計280レース）を`ingestion.batch --step results`で再同期した。
   - `ingestion.reconcile_duplicate_races --apply --expected-groups 77`で安全ガード付き統合を実施。
   - 最終状態はS3/L3欠損0件、対象期間の重複0組。旧キー76件を削除した。
2. **全期間候補を再学習した。**
   - 対象7,431レース、期間2022-01-05〜2026-05-31、`feature-set=v4`。
   - `lap_derived_ratio=1.0`、テストMAE 2.330、RMSE 3.020、バイアス -0.550。
3. **データ統合後の同一226レースで再比較した。**

| 指標 | 現行v4 | 候補v5_full |
|---|---:|---:|
| MAE | 4.592 | **3.881** |
| バイアス | **+2.571** | +2.628 |
| 展開ラベル的中率 | 71.7% | **79.2%** |
| ハイ再現率 | 88.7% | **95.7%** |
| 平均再現率 | **77.4%** | 66.0% |
| スロー再現率 | 32.8% | **58.6%** |
| PAI最上位帯リフト | 1.18x | **1.26x** |
| 有利−不利の好走率差 | +1.4% | **+2.6%** |

4. **採用を見送った。**
   - 事前基準の主指標だったバイアスが`+2.571→+2.628`と縮小しなかった。
   - MAE・分類・PAI・展開有利度は有望だが、評価後に基準を変更せず、既定
     `rpci_lgbm_dirt_v4.txt` / `lgbm-dirt-v4-lap-history`を維持した。
   - 候補モデルはコミットしていない。Windows実行機には
     `apps/api/models/rpci_lgbm_dirt_v5_full.txt`と来歴JSONが比較用に残っている。
5. **再学習世代の追跡を実装した。**
   - `scripts/train_rpci_lgbm.py`へ`--model-version`を追加し、来歴JSONへ保存する。
   - `lgbm_forecaster.py`は来歴JSONの`model_version`を優先し、来歴がない旧モデルは
     特徴量セットから従来世代を決める。
   - これにより同じv4特徴量の再学習候補もバックテスト上で別世代として識別できる。

### 対象ファイル

- `apps/api/scripts/train_rpci_lgbm.py`
- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
- `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`
- `apps/api/tests/unit/test_train_rpci_lgbm.py`
- `tasks/current.md`
- `docs/DECISIONS.md`
- `docs/HANDOFF.md`

### 仮実装・暫定値・未確定仕様・既知事項

- `v5_full`は不採用候補で、本番モデルではない。MAEなどの副指標を優先して採用基準を変える場合は
  新しい独立期間で再検証し、別ADRとして明示すること。
- バイアス`+2.571`は現行v4にも残る。単純な学習件数拡大では解消しなかった。
- `MODEL_VERSION_DIRT_V5`は来歴付き候補を識別するため定義したが、既定パスはv4のまま。
- 次候補のダート固有特徴量は未確定。`tasks/backlog.md:161`の着手条件を先に再確認すること。
- Windows実行機のDBは重複統合済みだが、これはGit管理外の実データ変更である。

### テスト結果

- API関連4ファイル: **78 passed**
- API単体・契約: **622 passed**
- `ruff check src tests scripts`: pass
- `mypy src --strict --python-version 3.12`: 0 issues（65 files）
- pytestはサンドボックスの`.pytest_cache`書き込み拒否警告1件のみ。テスト結果への影響なし。
- 実データ再同期: 4週末、各70レース成功、失敗0。
- 重複統合後診断: S3/L3欠損0、重複0組。

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`先頭の「ダートRPCI再学習候補を評価」
2. `docs/DECISIONS.md`末尾のADR-2026-08-02
3. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`の
   `_model_version_from_provenance()`と`SplitLightGBMRpciForecaster`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/pace/test_lgbm_forecaster.py tests/unit/test_train_rpci_lgbm.py -q
```

### 次に実施する具体的な手順

1. 新規のダート特徴量へ進む前に、`tasks/backlog.md:161`の着手条件をユーザーと確認する。
2. 着手する場合は`train_rpci_lgbm.py`のv4を直接変更せず、新しい特徴量セットとして分離し、
   同じ2026-06-01以降226レースでv4・v5_full候補と比較する。
3. 既知P0だった`main()`の`sent_fail`終了コード未反映は、2026-08-03に失敗回帰テストから修正済み。

## 2026-08-02 (Claude Code → OpenAI Codex) 引き継ぎ ★最初にここを読む

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- ブランチ: `claude/sweet-einstein-ilnaov`
- 最新コミット: `c89f902`（origin へ push 済み・作業ツリーはクリーン）
- 本セッションのコミット: `7e10be2`〜`c89f902` の16件

### ⏳ Codexが最初にやること（詳細は末尾「再開手順」）

**ユーザーのWindows実行機でダートRPCIモデルの再学習が実行中。**
その学習ログ（テストセット精度と`lap_derived_ratio`）を受け取るところから再開する。
**学習ログを見る前に新規実装を始めないこと。** 次の判断がその数値に依存する。

### 本セッションで何が起きたか（要約）

一般公開に向けた完成度評価を起点に、中核指標の不具合を1件発見して修正し、
ルールの前提そのものを実測で見直した。

1. **`rpci_actual`の算出式が途中で切り替わっていた**（最重要）。
   ラップ(S3/L3)があればTARGET準拠式、無ければ全馬PCI平均のフォールバックへ縮退する
   2経路があり、**ダートで平均5.4pt乖離**する。ラップ保有率は2022〜2024年0%・2026年100%で、
   年をまたぐRPCI比較が「式の違いを競馬側の変化」と取り違えていた。
   → ユーザーが全期間（2022-01-01〜2025-07-23）を`--step results`で再取り込みし、
   **全期間がラップ由来へ統一**された。副次効果として`rpci_actual`の外れ値が96件→**0件**。
2. **展開有利度は前付け馬にしか効いていなかった**。式統一後の全期間検証で、
   差し・追込は帯別好走率が平坦〜逆行し、係数をどう弱めても単調にならないと判明。
   → **ADR-0010 を採用し`style-advantage-v4`へ**（差し・追込は常に互角）。
3. **UI表示も実態へ合わせた**（ドメイン修正より先に実施）。差し・追込は「有利/不利」と
   断定せず「展開の影響は小さい」と表示し、スコア数値と進捗バーを出さない。
4. **同期プリフライトへ読み取り元MySQLの疎通確認を追加**（MySQL80停止時の遠回りを解消）。
5. **モデルに学習来歴を残すようにした**（1.の再発防止）。

### 数値で見た変化

| 指標 | 修正前 | 現在 |
|---|---|---|
| 展開有利度（本番条件・全体） | **-12.8%** | **+1.7%** |
| 同（ダート / 芝） | -16.8% / -9.8% | +2.3% / +1.8% |
| ダート想定RPCI MAE | 5.522 | 4.529 |
| ダート想定RPCI バイアス | +4.309 | **+3.373**（まだ大きい） |
| `rpci_actual` 外れ値 | 96件 | **0件** |
| 統合順位 1位馬勝率/好走率 | 21.5% / 51.5% | 19.0% / 50.5%（実質変化なし） |

### ⚠️ 未解決・既知の問題（重要な順）

1. **ダート想定RPCIのバイアス +3.373 が残る。** ダート中立点43.0に対し閾値帯は40〜46
   （幅6pt）なので、判定が系統的にスロー側へずれる。**原因はほぼ確実に、ダートモデルの
   学習データに旧式`rpci_actual`が混ざっていること**（学習は2026-06-01以前＝バックフィル前）。
   → **これが現在再学習中の対象。** 本セッションの残作業はここだけ。
2. **展開有利度は本番条件で+1.7%しかない。** オラクル条件（実績ペースを与えた場合）では
   +8.5〜10.2%あるので、**予測誤差がシグナルの8割以上を食っている**。1.の解決で改善する見込み。
3. **統合順位は1番人気（勝率約32%・複勝率約63%）に届いていない。** 19.0%/50.5%。
   `style_advantage`は表示専用で統合順位には入っていないため、今回の修正は効いていない。
4. **ダートは現行でも前付けの帯別好走率が単調にならない。** 係数ではなくダート固有の
   別要因。ADR-0010の対象外として切り離してある。
5. **`batch.py`の`results`送信失敗がexit 0に埋もれる問題は修正済み。** 2026-08-03に
   `main()`へ成功・失敗件数の集計と非ゼロ終了を追加し、失敗回帰テストで確認した。
6. **2025年のみ取り込みが不完全。** ラップ保有率が芝94.8%・ダート97.6%（約77レース）。
   同年だけ脚質未設定%も突出（芝5.5%）しており、成績が正しく取り込まれていないレース群が
   存在する。別途追跡が必要。
7. **`-PreflightOnly`の実動作は確認済み。** 2026-08-03にWindows実行機でAPI／PostgreSQLと
   読み取り元MySQL（83テーブル）を確認し、exit 0で終了した。

### 🧪 仮実装・未確定仕様

- **`StyleAdvantageWeights`**: 差し0.0/追込0.0はADR-0010で**確定**。
  `escape_gain=1.2` / `front_gain=1.0` / `slope_per_point=4.0` / クランプ[5,95] /
  `escape_crowd_penalty=6.0`は引き続き🧪暫定。
- **`AbilityWeights`**: `recent_races=5`維持（10走候補は実DB比較で不採用）。
  成分ブレンド（form0.55/賞金0.30/人気0.15）は`form-only`が2期間・全指標で上回ったが、
  母数拡大による結論反転が初見のためユーザー判断で**採用見送り・様子見**。
  `--compare-ability-weights`に候補は残してある。
- **`RuleWeights`のダート閾値40.0/46.0・中立点43.0**: 式統一後の分布でも
  スロー側割合は50.7〜57.7%とおおむね半々で、再較正は不要と判断した（変更していない）。
- **`PaiWeights`**、`_NEIGHBOR_BLEED_RATIO`、`FormationWeights`、`STALE_AFTER_DAYS`:
  従来どおり🧪暫定（本セッションで触れていない）。

### 検証結果（すべてこの引き継ぎ時点で実行）

| 対象 | 結果 |
|---|---|
| API `pytest tests/unit/ tests/contract/` | **620 passed** |
| ingestion-worker `pytest tests/` | **249 passed** |
| Web `npm run test` | **136 passed**（19ファイル） |
| API `ruff check src/ tests/ scripts/` | pass |
| ingestion `ruff check src/ tests/` | pass |
| API `mypy src/ --strict` | **0エラー**（65ファイル） |
| `lint-imports` | 2 kept, **0 broken** |
| Web `typecheck` / `build` | pass / success |

**既存の（本セッション以前から存在する）型エラー**（いずれも`src/`外のため
CLAUDE.mdの基準には抵触しない。本セッション前後で同数であることを確認済み）:
- `apps/api/scripts/` 6件（`backtest_forecast.py` no-redef 1、`repair_rpci.py` 2、
  `train_rpci_lgbm.py` lightgbm callbacks 1 ほか）
- `apps/ingestion-worker/src/ingestion/client/windows_client.py` 3件（has-type）

### 再開手順（Codexが最初に実行するコマンド）

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest tests/unit/ tests/contract/ -q
```

そのうえで、**ユーザーから再学習ログを受け取ってから**下記「Codexへの引き継ぎ事項」へ進む。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `docs/adr/0010-style-advantage-asymmetry.md`（Accepted・実測値と全経緯）
3. `docs/SPEC.md` §3.4（🚨2項目＋一次データ）
4. `apps/api/scripts/train_rpci_lgbm.py`（`_write_training_provenance`）
5. `tasks/current.md`

## 2026-08-02 (Claude Code) 同期プリフライトへ「読み取り元MySQL」の疎通確認を追加

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex

### 背景（実際に発生した事象）

ユーザーが手動同期を実行したところ、MySQL80サービスが停止していたため失敗した。
問題は失敗したこと自体ではなく、**原因に辿り着くまでの遠回り**だった。

1. プリフライトが「API と PostgreSQL は ready」と表示して通過
2. `mykeibadb.exe` が7秒で **exit 0**（MySQLが無いので実際には何もできていない）
3. `batch.py` が接続拒否で落ち、30秒・60秒待って3回リトライ

プリフライトが確認していたのは**書き込み先だけ**で、肝心の**読み取り元**を
見ていなかった。「準備OK」と出た直後に接続拒否で落ちるため、かえって紛らわしい。

### 実施内容

- `src/ingestion/check_mykeibadb.py`（新規）
  - `batch.py`と同じ`MyKeibaDbConfig.from_env()`で実際に接続し、
    `SHOW TABLES`まで確認する。設定の解釈がズレない。
  - TCPポート疎通ではなく実接続にしたのは、サービス停止（§6.1）だけでなく
    認証失敗（§6.2）・DB名違いも同じ入口で捕まえるため。
    エラーコード（2003/1045/1698/1049）で分類し、MANUAL_SYNC_GUIDEの該当節へ誘導する。
  - テーブル0件も失敗扱い。初回取り込みが走っていない空DBを「正常」と誤判定しないため。
  - pymysqlは任意extra（`.[mysql]`）なので、importは関数内で行い未インストール時は
    インストールコマンドを表示する。
- `scripts/run_mykeibadb_full_sync.ps1`
  - `Test-MykeibadbReadiness`を追加し、`mykeibadb.exe`起動前に実行する。
  - `2>&1`で拾ったstderrをPowerShellが終了エラーにしないよう、
    呼び出し中だけ`$ErrorActionPreference`をContinueへ落とす
    （`run_batch.ps1`が既に同じ対処をしている既知の罠）。
- `MANUAL_SYNC_GUIDE.md`
  - プリフライトが読み取り元も見ることを明記し、単独実行コマンドを追加。
  - §6.1へ「services.msc から起動するのが最速」を追記
    （PATHに依存しないため、MySQL Workbenchが`Unable to execute command chcp`で
    使えない状態でも起動できる。これはWorkbench側のPATH問題で、MySQL本体とは別件）。

### 検証

- ingestion 249 tests（新規10件）、ruff 全pass。
- `mypy src/ --strict`: 新規ファイルは0エラー。既存の`windows_client.py`に3件の
  エラーが残るが、これは本変更以前から存在する（stashして確認済み）。
- PowerShell実動作は2026-08-03にWindows実行機で確認済み。初回確認でPython日本語出力の
  文字化けを検出し、同期ラッパーのUTF-8設定追加後に再実行して解消を確認した。

### 未確認・次にやること

- `-PreflightOnly`での実動作確認は2026-08-03に完了。
- 関連する既知の穴だった`batch.py`の`results`送信失敗のexit 0埋没は、
  2026-08-03に終了コード1へ伝播するよう修正済み。

## 2026-07-26 (14) (Claude Code) ✅ ADR-0010 採用 — style-advantage-v4（後方脚質は採点しない）

- 作業担当: Claude Code（実DB検証はユーザーがWindows実行機で実施）
- 引き継ぎ先: OpenAI Codex
- 追加コミット: `7ecfed4`（脚質別係数と候補比較CLI）/ `562dcf9`（比較の欠陥修正）/
  `deae219`（自在の取り下げ）/ 本コミット（採用）

### 検証と決定

独立2期間（2022〜2024 / 2025〜2026-07）× 芝・ダートの4条件で
`--compare-style-advantage-weights`を実行し、候補を比較した。

| 候補 | 芝22-24 | ダ22-24 | 芝25-26 | ダ25-26 |
|---|---|---|---|---|
| closer-weak | +2.9% | +0.0% | +2.7% | +1.1% |
| closer-mild | +0.9% | +0.2% | +1.4% | +0.2% |
| flexible-only | +0.8% | +0.3% | +0.1% | **-0.8%** |
| measured | +2.6% | +0.3% | +1.3% | **-0.6%** |
| **back-neutral** | **+8.1%** | **+3.4%** | **+4.0%** | **+0.6%** |

**`back-neutral`（差し・追込を常に互角）を採用**し、`style-advantage-v4`とした。

### 当初の提案から変わった点（重要）

1. **自在の採点対象化は取り下げた。** 一次データでは自在が先行と同等に反応していたが、
   実際に採点すると直近ダートで悪化（-0.8%/-0.6%）し、自在自身の帯別単調性も
   4条件中1条件でしか成立しなかった。**「ペースに反応する」ことと
   「有利不利の分離に貢献する」ことは別**だった。
   → `entries`は4件のままで、**API公開スキーマとWeb表示への影響はなくなった**。
2. **ADRに書いた採用条件のひとつが誤りだったため改訂した。**
   「差し追込グループが単調であること」は、後方を順序づけないと決めた候補に対しては
   原理的に満たせない。単調性は候補が順序づけを主張しているグループにのみ課す。
3. **比較ツール自体にも欠陥があり、先に直した**（`562dcf9`）。
   自在がどのグループにも属さず単調性を確認できなかった点と、
   `stalker_gain=0`が差しを1帯へ潰して判定を無意味にしていた点。

### 実装内容

- `domain/pace/style_advantage.py`
  - 既定を`stalker_gain=0.0` / `closer_gain=0.0`へ（差し・追込は常に50）。
    `escape_gain=1.2` / `front_gain=1.0`は据え置き（前付け側は実測と整合していた）。
  - `MODEL_VERSION`を`style-advantage-v4`へ。
  - `reasons`の文言から「ハイ→後ろが有利」を削除し、前付けについて言えることだけを述べる。
- OpenAPI / `packages/api-client`を再生成（`model_version`の説明文のみの差分）。
- 2026-07-26にUI層で先行実施した「差し・追込は展開の影響は小さい」という表示が、
  これでドメインの挙動と一致した（スコアが常に50＝互角）。

### 検証

API 616 tests・ruff・mypy --strict（65ファイル）・lint-imports、
Web 136 tests・typecheck・production build すべて成功。

### 残課題

- **ダートは現行でも前付けの帯別好走率が単調にならない。** 係数ではなく
  ダート固有の別要因。本件と切り離して追う必要がある。
- 有利／不利ラベルが付く馬は減る（芝で全体の約3割）。主張の数は減るが精度は上がる。
  実運用で体感を確認したい。
- `escape_gain`/`slope_per_point`/クランプ幅は引き続き🧪暫定。

### Codexが最初に確認するファイル

1. `docs/adr/0010-style-advantage-asymmetry.md`（Accepted・全経緯と実測値）
2. `docs/SPEC.md` §3.4
3. `apps/api/src/pci/domain/pace/style_advantage.py`

## 2026-07-26 (13) (Claude Code) 🚨 展開有利度は「前付け馬」にしか効いていないと判明（要設計判断）

- 作業担当: Claude Code（実DB実行はユーザーがWindows実行機で実施）
- 引き継ぎ先: OpenAI Codex
- 追加コミット: `f4ff23e`（帯別集計）/ `34ee306`（脚質グループ別集計）
- 前提: (12)のバックフィル完了後、全期間が同一式になった状態での再検証

### バックフィルの結果（(12)の続き）

ユーザーが2022-01-01〜2025-07-23の`--step results`を再実行し、`rpci_actual`が
全期間でラップ由来（TARGET準拠）に統一された。

- ダートの1〜7月平均は2022〜2026年で41.1〜42.0へ収束（旧: 2022〜2025年45.9〜46.2 / 2026年42.0）。
  **「2026年にダートが激変した」という現象は式の違いだったと確定**。
- 副次効果: `rpci_actual`の外れ値が96件→**0件**（最小2.00/最大96.90 → 20.90/72.00）。
  ラップ由来式は個々の馬のタイム異常の影響を受けず、フォールバックより頑健。
- 残課題: 2025年のみラップ保有率が芝94.8%・ダート97.6%と未達（約77レース）。
  同じ2025年だけ脚質の未設定%も突出（芝5.5%・ダート3.0%、他年0.7〜1.0%）しており、
  **成績が正しく取り込まれていない2025年のレース群が存在する**。別途追跡が必要。

### 統一後の再検証で判明したこと

`--validate-style-advantage`で全期間（芝63,646頭・ダート70,942頭）を再測定した結果、
**旧来の「ダートで+8〜12pt」は較正ずれによる見かけの数字**だったと確定した。

| | 旧測定 | 統一後 |
|---|---|---|
| 芝 全体 | +4.6% | **+2.9%** |
| ダート 全体 | +8.9% | **+2.9%** |

旧ダートの高い数字は、82%のレースが「スロー＝前有利」と判定されていたため、
**「ペースを読めていた」のではなく「ダートは前が止まりにくい」という恒常傾向を
拾っていただけ**だった。

### 🚨 核心的な発見: 有利度は前付け馬にしか効いていない

脚質グループ別の帯集計（`34ee306`で追加）で、対ベース好走率が以下と判明した。

| グループ | 不利 | やや不利 | 互角 | やや有利 | 有利 |
|---|---|---|---|---|---|
| 芝・前付け（19,388頭） | 0.84x | 0.89x | 1.02x | 1.07x | **1.18x** |
| ダート・前付け（18,598頭） | 0.94x | 0.88x | 0.96x | 1.03x | **1.14x** |
| 芝・差し追込（44,258頭） | 1.03x | 0.99x | 0.98x | 1.01x | **0.98x** |
| ダート・差し追込（52,344頭） | 0.94x | 0.99x | 1.03x | 1.08x | **1.02x** |

- **前付けは両コースとも単調**で、芝は0.84x→1.18xと大きく分離する。
- **差し追込は芝で完全に平坦**（0.98〜1.03x、しかも「不利」帯が最高）、
  **ダートは「有利」帯で逆行**する。
- 全体の+2.9%は**前付け馬だけが稼いでいる**。差し追込は出走頭数の70〜74%を
  占めるがシグナルがなく、ダート相関-0.000・芝+0.037の主因はここ。
- 解釈: 「スロー→前が楽に運べる」は成立するが、「ハイ→差しに向く」は成立しない。
  ペースが速いことは前が苦しくなる理由にはなっても、特定の差し馬が届く理由にはならない。

### 併せて判明: ベースライン好走率が脚質で約2倍違う

| | 前付け | 差し追込 |
|---|---|---|
| 芝 | 33.9% | 18.2% |
| ダート | 33.9% | 15.9% |

有利度スコアは全馬50中心のため、この差を全く表現していない。
**スコア70の差し馬（実力16〜18%）を「有利」、スコア30の逃げ馬（実力32%）を「不利」と
表示している**状態で、展開恩恵馬の抽出や統合順位にも波及している可能性がある。

### 変更ファイル

1. `apps/api/src/pci/application/backtest.py`
   - `StyleAdvantageBand` / `StyleAdvantageGroupBands`を追加し、`StyleAdvantageLift`へ
     `bands`（表示ラベル別）と`style_groups`（前付け／差し追込別）を持たせた。
   - 帯の境界は web の`styleVerdict`と同一（等間隔帯にしない）。境界一致を検証するテスト付き。
   - `StyleAdvantageSample`へ`running_style`を追加（既定None・既存呼び出しは非破壊）。
2. `apps/api/tests/unit/application/test_backtest.py`（帯境界・帯合計・脚質分割の3件を追加）
3. `docs/SPEC.md` §3.4、`docs/HANDOFF.md`（本節）、`tasks/current.md`

**ドメイン層のコード・係数は一切変更していない。**

### 実施した暫定対応（ユーザー判断で「UI表示だけ先に直す」を選択）

ドメイン層のスコア算出・係数は**一切変更していない**。表示だけを実態へ合わせた。

- `apps/web/src/lib/pace.ts`: `StyleAdvantageScore`へ`isDirectional`/`note`を追加。
  `DIRECTIONAL_STYLES`（逃げ・先行）以外は verdict を「展開の影響は小さい」に置換する。
  判定を1箇所に閉じたので、PC・スマホ双方が同じ基準になる。
- `RaceForecastDashboard.tsx` / `MobileRaceForecastDashboard.tsx`:
  差し・追込では**スコア数値と進捗バーを描画しない**。文言で「影響は小さい」と書いても
  大きな数値と満杯のバーが並ぶと視覚が勝って「有利」と読まれるため。
  理由文はリスト下に一度だけ置く（脚質ごとに繰り返さない）。
- `PaceProfileChart.tsx`: `muted`フラグを追加し、差し・追込は淡色＋「（参考）」表示。
- ハイペース時の文言から裏付けのない主張を外した
  （「差し・追い込みが届きやすい」→「前に行く馬には厳しい」等）。
  スロー時の「逃げ・先行が粘りやすい」は実データが支持するため変更していない。
- 検証: Web 136 tests（新規2件・既存1件を新仕様へ更新）、typecheck、build成功。
  Playwrightで実コンポーネントをレンダリングし、PC・スマホ・プロファイルの3箇所を目視確認。

### 一次データの測定と ADR-0010 の起票

ドメイン是正の判断材料が、有利度スコア経由の測定しかなかった（＝現行ルールの
答え合わせしかできない）ため、`--pace-style-matrix`を追加した（commit `baad549`）。
実績ペース×確定脚質の素の好走率を、有利度ルールを介さず集計する。
自在は有利度の対象外だが出走の3割超を占めるため集計対象に含めた。

**実測結果（2022-01-01〜2026-07-21、芝101,478頭・ダート107,828頭）**

「スロー−ハイ」の差（各脚質の自平均に対する比）:

| 脚質 | 芝 | ダート | 現行の乗数 | 実測から示唆される乗数 |
|---|---|---|---|---|
| 逃げ | +0.33 | +0.15 | +1.2 | 約 +1.3 |
| 先行 | +0.19 | +0.16 | +1.0 | +1.0 |
| **自在** | **+0.17** | **+0.11** | **採点対象外** | 約 **+0.8** |
| 差し | +0.05 | -0.04 | -1.0 | 約 **0.0** |
| 追込 | -0.05 | -0.09 | -1.2 | 約 **-0.4** |

- **ペース感応度は脚質間で最大6倍以上違う**。前後対称の単一係数は実態と合わない。
- **自在は先行とほぼ同等に反応するのに、まったく採点されていない**。
  出走頭数の34〜37%を占める最大グループであり、機会損失が大きい。
- 差し・追込の反応は前付けの1/4以下。現行の-1.0/-1.2は過大。
  前付け側の係数は概ね妥当で、**壊れているのは後方側と自在の欠落**。

これを根拠に **`docs/adr/0010-style-advantage-asymmetry.md`（Status: Proposed）** を起票した。
係数の具体値はADR内でも確定しておらず、`--compare-rule-weights`と同じ手順で
独立2期間の検証後に採用する方針を明記している。

### 次にやること（ADR-0010の採否をユーザーが判断）

採用する場合の影響範囲:

- `StyleAdvantageWeights`を脚質ごとの独立係数へ（現行は`escape_gain`/`closer_gain`の2つ）。
- `_SCOREABLE_STYLES`へ`FLEXIBLE`を追加し、`entries`が4件→5件になる。
  **API公開スキーマとWeb表示が変わる**（OpenAPI/api-client再生成、
  `PaceProfileChart`・展開分析カードの5行対応が必要）。
- 採用条件は ADR-0010「採用条件」節を参照（両グループ単調・両コースで現行以上・
  独立2期間で再現）。

**判断までドメイン層の係数・設計は変更しない。**

既知の未検証点: 自在は「どの分類にも寄らない」残余カテゴリであり、
`running_style.py`の判定閾値そのものの妥当性は未検証。判定精度が低ければ
採点しても効果が出ない可能性がある（ADR-0010のNegativeに記載）。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節と(12)）
2. `docs/SPEC.md` §3.4 の🚨2項目
3. `apps/api/src/pci/domain/pace/style_advantage.py`
4. `apps/api/src/pci/application/backtest.py`（`_summarize_style_advantage_groups`）

## 2026-07-26 (12) (Claude Code) 🚨 展開有利度のダート崩壊は「rpci_actual の算出式切替」が原因と特定

- 作業担当: Claude Code（実DB実行はユーザーがWindows実行機で実施）
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 追加コミット: `7e10be2` / `1d33c3f` / `962a369`（`scripts/diagnose_rpci.py`の診断拡張）

### 発端

一般公開に向けた完成度評価の一環でバックテスト出力を精査したところ、
展開有利度（`style-advantage-v3`）が2026年前半で逆相関になっていた
（直近300レース混合で -10.7pt、芝 -9.9pt、ダート -11.8pt）。
本プロダクトの中核指標のため、公開可否に直結する問題として切り分けを行った。

### 切り分けの経過（すべて実DB・ユーザー実行）

1. `--diagnose-style-advantage`（4パターン）で2026年前半を診断。入力を確定値に
   置換しても改善せず、当初は「ルール自体の問題」と判断した。**この判断は誤り**で、
   `--limit 300`がコース別だと直近2ヶ月しか見ておらず、期間の切り取りが原因だった。
2. `--validate-style-advantage --style-breakdown year`（2022〜2026、芝61,919頭・
   ダート70,000頭）で、**ルールは5年間・両コースで一貫して有効**と判明
   （芝+3.1〜+6.1pt、ダート+7.7〜+11.9pt）。2026年のダートだけ+2.9ptへ低下。
3. 同一月窓（5〜7月）で前年と比較。芝は2025年+2.5%→2026年+4.4%で問題なし。
   **ダートのみ2025年+18.8%→2026年-0.6%**。季節性ではないと確定。
4. `scripts/diagnose_rpci.py --by-track-year`を新規追加して分布を直接観測。
   当初は通年と部分年（2026年は1〜7月のみ）を並べる交絡があったため、
   `--month-from/--month-to`を追加して月窓を揃えた（`1d33c3f`）。

### 確定した原因

`aggregate_rpci`（`domain/pace/pci.py`）には**2つの算出経路**がある。

- レースラップ由来（`race_s3f`/`race_l3f`あり）: TARGET準拠の正式式
- フォールバック: 全完走馬PCIの平均（docstring上も「暫定」）

この2経路は**ダートで平均5.4pt乖離する**（2025年1〜7月の同一期間内比較で
ラップ由来40.9／代替46.3）。芝は約1.6ptしか離れない。

ラップ保有率（1〜7月）:

| 年 | 芝 | ダート |
|---|---|---|
| 2022〜2024 | 0.0% | 0.0% |
| 2025 | 4.0% | 2.8% |
| 2026 | **100.0%** | **100.0%** |

2025-07-24以降のラップバックフィル境界と一致する。つまり**2026年のダート平均42.0は
競馬の変化ではなく、式がフォールバックからラップ由来へ全面的に切り替わった結果**。

ダートの中立点43.0（閾値40.0/46.0の中点）は旧フォールバック分布で較正されていたため、
新分布とは合わない。中立点に対する「スロー側」割合が82%前後→57.7%へ動き、
「有利」と判定される馬が24%→42%に増えて選別力を失った。
芝が壊れていないのは、2経路の差が小さく較正がほぼそのまま通用するため。

### 判明した副次的な含意

- **年をまたぐRPCI関連のバックテストは式の違いを含む**ため、絶対値の比較は
  そのままでは成立しない（候補同士を同一データで比べる相対比較への影響は限定的）。
- `--monitor-dirt-v4`で観測されていた想定RPCIバイアス+4.071は、この文脈で
  再評価が必要（学習データと評価データで式が混在している可能性）。
- 現時点の**ダートの展開分析はユーザーに誤った内容を表示している**状態。

### 変更ファイル

1. `apps/api/scripts/diagnose_rpci.py`（`--by-track-year` / `--month-from` /
   `--month-to` を追加。RPCI分布・確定脚質構成比・算出経路の3表を出力）
2. `docs/SPEC.md` §3.4（🚨項目を追加。2026-07-23時点の「開催条件に局在」という
   解釈は見直しが必要と明記）
3. `docs/HANDOFF.md`（本節）、`tasks/current.md`

ドメイン・アプリ層のコードは変更していない。閾値・中立点も**変更していない**
（対処方針が未確定のため、独断で較正しない）。

### 次にやること（未実施）

1. **mykeibadbが2022〜2025年のラップを保持しているか確認**する。
   ```cmd
   cd apps\ingestion-worker
   .venv\Scripts\python.exe -m ingestion.diagnose_lap_coverage --date 20220101 --date-to 20250723
   ```
   - 保持していれば → 全期間をバックフィルして式を統一し、そのうえでダート閾値を再較正する。
     全期間の履歴が同一式になるため、モデル再学習と過去バックテストの信頼性も回復する。
   - 保持していなければ → ラップ由来分布（2025-07-24以降）だけでダート閾値40.0/46.0を
     較正し直す。標本は約1年に限られる。
2. 対処が入るまでの暫定措置として、ダートの`reliability`を`reference`に落として
   表示上の強い推奨を避けるかを検討する（既存機構で実装可能）。
3. ダートRPCI v4モデルの学習データに旧式が混在していないか確認する。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `docs/SPEC.md` §3.4 の🚨項目
3. `apps/api/src/pci/domain/pace/pci.py`（`aggregate_rpci`の2経路）
4. `apps/api/src/pci/domain/pace/style_advantage.py`（`neutral_rpci`）
5. `apps/api/scripts/diagnose_rpci.py`

## 2026-07-26 (11) (Claude Code) 成分ブレンド重み再検証（2026-07-22と同日付区切り・母数拡大） → 採用は様子見

- 作業担当: Claude Code（実DB実行はユーザーがWindows実行機で実施）
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 前提: (10)で発見した「2026-07-22の成分ブレンド結論との食い違い」の追跡調査

### 経緯

(10)の`recent10`検証と同じ2回の実行で、成分ブレンド候補`form-only`/`form-heavy`が
たまたま両期間・全指標改善という結果だった。ただし使った日付区切り
（直近200件・〜2025-12-31以前200件）が2026-07-22の比較
（2025-07-01〜12-31・2026-01-01〜07-21）と異なるため、即断せず同じ日付区切りで
再検証することをユーザーに確認し、実施した。

### 実DB再検証結果（`--date-from`/`--date-to`を2026-07-22と揃え、`--limit 300`）

母数は2026-07-22時点より増加している（2025-07-01〜12-31: 212→300件、
2026-01-01〜07-21: 97→300件。データ蓄積が進んだため）。

| 候補 | 2025-07-01〜12-31 (300件) | 2026-01-01〜07-21 (300件) | 判定 |
|---|---|---|---|
| form-only | +0.7% / +2.7% / +0.9% | +2.3% / +0.7% / +1.3% | 両期間・全指標改善 |
| form-heavy | -0.3% / +1.0% / +0.5% | +1.7% / +2.3% / +0.8% | 前半期間の1位勝率のみ悪化 |
| market-aware | +0.0% / +0.3% / +0.0% | -1.3% / -4.0% / +0.0% | 後半期間で明確に悪化 |
| recent10 | +1.0% / +1.0% / -0.8% | +0.0% / -1.3% / -0.5% | 両期間TOP3捕捉率が悪化（(10)の不採用判断を再確認） |

（列は1位勝率(差)／1位好走率(差)／TOP3捕捉率(差)）

### 判断: 今回は採用を見送り、現行ブレンド（form0.55/本賞金0.30/人気0.15）を維持

- `form-only`は同じ日付区切りでも両期間・全3指標が改善し、採用基準（両期間で
  全指標が悪化しないこと）を満たしている。2026-07-22時点は満たしていなかったため、
  母数拡大（212→300、97→300）で結論が反転した可能性がある。
- ただし母数拡大による結論反転は今回が初見で、安定して再現するかは未確認。
  ユーザーに採用可否を確認したところ、**「もう少し様子見」**を選択された
  （データがさらに増えた後の安定性を見てから判断したい）。
- コード変更なし。`AbilityWeights`のデフォルト（`weight_form=0.55` /
  `weight_prize=0.30` / `weight_popularity=0.15`、`ability.py:44`付近）は変更していない。

### 未実施・次の担当への引き継ぎ

データがさらに蓄積された時点（次回の実DB検証タイミング）で、同じ日付区切り
（2025-07-01〜12-31、2026-01-01〜07-21）または新しい直近期間で`form-only`が
引き続き両期間・全指標を改善するか再確認すること。安定して再現するなら
`AbilityWeights`のデフォルトを`weight_form=1.0`/`weight_prize=0.0`/
`weight_popularity=0.0`へ変更し、関連テスト・ゴールデン値を更新する。

### 変更ファイル

1. `docs/SPEC.md`（§9-16 に再検証結果を追記）
2. `docs/HANDOFF.md`（本節）
3. `tasks/current.md`

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `docs/SPEC.md §9-16`
3. `apps/api/src/pci/domain/pace/ability.py`（`AbilityWeights`のデフォルト値）

## 2026-07-26 (10) (Claude Code) 地力(ability)参照走数10走の実DB検証結果 → 不採用、5走を維持

- 作業担当: Claude Code（実DB実行はユーザーがWindows実行機で実施）
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 前提: (9)で追加した`recent10`候補・不具合修正の実DB検証

### 実DB比較結果（ユーザー実行、`--compare-ability-weights`）

2つの独立期間で`recent10`（`AbilityWeights(recent_races=10)`）と現行（5走）を比較。

| 期間 | 1位勝率(差) | 1位好走率(差) | TOP3捕捉率(差) |
|---|---|---|---|
| 直近200レース（〜2026-07-26） | 23.0%(+1.5%) | 50.5%(-1.0%) | 40.7%(-0.3%) |
| 〜2025-12-31以前200レース | 20.0%(+1.5%) | 41.5%(+1.5%) | 35.2%(-0.5%) |

### 判断: 不採用（`recent_races=5`を本番維持）

- 1位勝率は両期間で+1.5%と安定して改善。
- しかし**TOP3捕捉率は両期間とも悪化**（-0.3%/-0.5%）し、1位好走率は
  符号が不安定（-1.0%→+1.5%）。
- `RuleWeights`・`PaiWeights`・既存`AbilityWeights`ブレンド比率の検証と同じ基準
  （両期間で全指標が悪化しないことを採用条件とする）を満たさないため、
  `AbilityWeights.recent_races`のデフォルトは変更せず、現行5走を維持する。
- `recent10`候補は`DEFAULT_ABILITY_WEIGHT_PROFILES`に残す（データ蓄積後の
  再検証や将来のADR判断で再利用できるようにするため、削除しない）。

### 副次的な発見（今回は未決着・要ユーザー判断）

同じ2回の実行結果で、成分ブレンド候補`form-only`（近走100%）・`form-heavy`
（近走70%）が**両期間・全3指標を改善**していた（例: form-only 直近200で
+2.0%/+0.5%/+1.5%、〜2025-12-31以前200で+1.5%/+3.5%/+1.0%）。

これは2026-07-22に実施済みの同候補比較（2025-07-01〜12-31・212レース／
2026-01-01〜07-21・97レースで「両期間で全指標が改善する候補はなく現行維持」と
結論。0Bエントリ参照）と食い違う。期間の区切り方・母数が異なる比較であり、
どちらが正しい／再現性があるかは今回の2回（各200件・日付境界も異なる）だけでは
判断できない。**本セッションでは成分ブレンドの変更提案はせず、事実として記録するに
留める**。次に着手する場合は、2026-07-22と同じ日付区切り（2025-07-01〜12-31、
2026-01-01〜07-21）で再現するか確認してから判断すること。

### 変更ファイル

1. `docs/SPEC.md`（§9-16 に実DB検証結果と副次発見を追記）
2. `docs/HANDOFF.md`（本節）
3. `tasks/current.md`

コード変更はなし（判断の記録のみ）。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `docs/SPEC.md §9-16`
3. `apps/api/src/pci/application/backtest.py`（`DEFAULT_ABILITY_WEIGHT_PROFILES`）

## 2026-07-26 (9) (Claude Code) 地力(ability)の参照走数10走候補を準備（本番は5走のまま・重要なハードコード不具合を修正）

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景（ユーザー提案）

ユーザーから「統合順位予想で使う地力は近走5走を参照しているが、短すぎて、
本来得意なペースで走った6走目以降のデータを見落とす恐れがある。5走から10走へ
変更すべきではないか」との提案があった。

### 調査結果（ユーザーへ回答済み）

1. **「得意なペース」判定は既に5走に限定されていない**:
   - `affinity.py`の`build_horse_pace_affinity_profile`（PAI適性、「馬ごとの得意な
     レース質」）は`forecast_use_cases.py`の`_build_affinity_profile`経由で
     **最大12走**を参照している（好走＝3着以内・重賞なら5着以内のみ抽出）。
   - 前付けペース傾向（rule-v2）・前後半3F履歴（RPCI v4特徴量）は**10走**参照。
   - 5走に限定されているのは**「地力(ability)」と「脚質判定」の2つだけ**。
   ユーザーの提案対象を「地力」と確認した上で作業した。
2. **重要な副次発見（不具合）**: `AbilityWeights.recent_races`（現行5）を
   バックテスト等で変更しても反映されない不具合があった。
   `forecast_use_cases.py`の`_build_ability_score`が、`AbilityScorer`へ渡す前に
   独自に`history[:5]`とハードコードしており、`AbilityScorer.score()`内部の
   `[: w.recent_races]`スライスに実質的に到達する前に既に5走へ切り詰められていた。

### ユーザーとの合意事項

検証方針をAskUserQuestionで2案（比較ツールに10走候補を追加／検証を待たず
今すぐ10走へ変更）提示し、**「比較ツールに10走候補を追加（推奨）」**を選択された。
本番デフォルト（`recent_races=5`）は変更していない。

### 実施内容（`apps/api`）

- `application/forecast_use_cases.py`: `_build_ability_score`の
  `history[:5]`ハードコードを撤去し、`AbilityScorer`へ取得済み履歴を
  そのまま渡すよう修正（走数の決定は`AbilityWeights.recent_races`だけに委ねる）。
- `application/backtest.py`: `DEFAULT_ABILITY_WEIGHT_PROFILES`へ`recent10`候補
  （`AbilityWeights(recent_races=10)`、説明「参照走数を5走→10走へ拡大」）を追加。
  既存の`--compare-ability-weights`（`ForecastBacktester`経由で本番と同じ
  `ForecastRaceUseCase`を使う）が自動的にこの候補も比較する。
- `tests/unit/application/test_forecast_use_cases.py`: 上記不具合の回帰テストを
  追加。直近5走（1〜5走前）を不振の未勝利戦、6〜8走前をG1好走とする8走分の
  履歴を用意し、`recent_races=10`のスコアラーでは`sample_size=8`・
  地力スコアが現行（5走・不振のみ見る）より高くなることを確認する。
  日数はすべて180日以内（新しさ減衰の影響を排除）に収めた。

### 検証

- API 598 tests（新規1件）、ruff、mypy --strict（65ファイル）、
  lint-importsすべて成功。OpenAPI/schemaは変更していない
  （API契約に影響する変更なし、内部ロジックとバックテスト候補の追加のみ）。

### 未実施・次の担当への引き継ぎ

このクラウド環境からは実DB接続ができないため、以下はユーザー（Windows実行機）に
委ねる。

```cmd
cd apps\api
.venv\Scripts\python.exe -m scripts.backtest_forecast --limit 200 --compare-ability-weights
```

出力される`recent10`候補の1位馬勝率・1位馬好走率・TOP3捕捉率が、現行（5走）と
比べて2期間（できれば2025年後半・2026年前半など）で安定して改善するか確認する。
`RuleWeights`・`PaiWeights`・既存の`AbilityWeights`ブレンド比率と同様、
一方の指標だけ改善して他が悪化する場合は不採用とし、本番`recent_races=5`を維持する
方針で判断すること。採用する場合は`AbilityWeights.recent_races`の
デフォルト値を変更し、ゴールデンテスト・回帰テストの期待値を合わせて更新する。

### 変更ファイル

1. `apps/api/src/pci/application/forecast_use_cases.py`
2. `apps/api/src/pci/application/backtest.py`
3. `apps/api/tests/unit/application/test_forecast_use_cases.py`
4. `tasks/current.md`
5. `docs/HANDOFF.md`

`recent_races`自体は`docs/SPEC.md §9-16`に記載済みの🧪暫定係数の一部であり、
今回新たに仕様化・確定したものはないため`docs/DECISIONS.md`は更新していない。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/api/src/pci/application/backtest.py`（`DEFAULT_ABILITY_WEIGHT_PROFILES`）
3. `docs/SPEC.md §9-16`（AbilityWeightsの暫定係数一覧）

---

## 2026-07-26 (8) (Claude Code) スマホに統合順位予想（展開×能力）を追加

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景（ユーザー報告）

ユーザーがスマホ画面（注目馬タブ）のスクリーンショットを提示し、「PC版では展開・能力を
鑑みた全馬の総合予想順位が表示されるが、スマホでは見れない。これは仕様か」と質問した。

### 調査

`grep`で`IntegratedRankingView`の使用箇所を確認したところ、`RaceForecastDashboard.tsx`
（PC版、`検討サマリー`直後・`隊列予想`の前に配置）にしか組み込まれておらず、
`MobileRaceForecastDashboard.tsx`（スマホ版、サマリー/隊列/注目馬/詳細の4タブ構成）
には一度も追加されていなかった。統合順位予想はこのセッション前半にPhase1/2として
新規実装した機能で、その後（別セッションでのCodexによる）スマホ全面改修に
反映され忘れたのが原因（仕様ではなく実装漏れ）。

### ユーザーとの合意事項

追加先をAskUserQuestionで3案（注目馬タブへ追加／サマリータブ上部へ追加／
サマリーに上位3頭プレビュー＋注目馬に全頭表示の両方）提示し、
**「『注目馬』タブへ追加（推奨）」**を選択された。

### 実施内容（`apps/web`）

- `MobileRaceForecastDashboard.tsx`: 「注目馬」タブの先頭（既存の
  「展開恩恵馬TOP5」より前）へ`{forecast.integrated_ranking ? <IntegratedRankingView
  ranking={forecast.integrated_ranking} /> : null}`を追加した。サマリータブの
  内容・構成は変更していない。
- 副次対応: 枠色統一作業（前セッション(5)(6)）の際に見落としていた
  `IntegratedRankingView.tsx`自身の重複した枠色定義（独自の`FRAME_CLASS`、
  当時のgrep結果には含まれていたが実際の修正対象から漏れていた）を発見し、
  共有の`lib/pace.ts`の`frameColorClass()`へ統一した。枠順未確定
  （frame_no=0）時の表示も他画面と同じ「登録」表示へ揃えた
  （従来は生の`horse_no`をそのまま表示していた）。
- `IntegratedRankingView.tsx`にはテストが1件も無かったため、新規
  `IntegratedRankingView.test.tsx`を追加した（上位5件常時表示・6位以下折りたたみ、
  枠色バッジ、枠順未確定時の表示、分類/能力/展開適性タグ、エントリー0件時の
  非表示を検証）。

### 検証

- Web 134 tests（新規6件）、typecheck、production buildすべて成功。
- Playwright（`renderToStaticMarkup`＋ビルド済みTailwind CSS）で、
  「注目馬」タブの実際の構成（統合順位予想＋展開恩恵馬TOP5を同一ページに
  再現。`MobileRaceForecastDashboard`は非アクティブタブをSSRで描画しないため、
  同じ構成をこのファイルの外で組み立てて確認）を390px幅でスクリーンショット確認。
  横はみ出し無し、タグが多い行（3位など）も`flex-wrap`で自然に折り返すことを確認した。
  一時プレビューファイルは確認後に削除済み。

### 変更ファイル

1. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
2. `apps/web/src/components/IntegratedRankingView.tsx`
3. `apps/web/src/components/IntegratedRankingView.test.tsx`（新規）
4. `tasks/current.md`
5. `docs/HANDOFF.md`

新しい設計判断（追加先タブ）はユーザーとのAskUserQuestionで確定済みのため
`docs/DECISIONS.md`は更新していない。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/web/src/components/MobileRaceForecastDashboard.tsx`

---

## 2026-07-26 (7) (Claude Code) ダートレースの展開速度誤判定を修正（重要バグ）

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景（ユーザー報告）

ユーザーがスマホ画面（中京7R 東海ステークス、ダート1400m）のスクリーンショットを提示し、
「画面上部では『平均ペース』と記載されているが、詳細タブの展開は『かなり速い流れ』と
なっている。この違いは何か」と報告した。

### 原因

ペース速度の判定ロジックが**バックエンドとフロントエンドで別々に実装され、食い違っていた**。

- バックエンド`classify_pace()`（`apps/api/src/pci/domain/pace/rpci_forecast.py`）は、
  芝・ダートで別々の閾値を使う設計（rule-v4）: 芝は高49.0/低51.0、ダートは高40.0/低46.0
  （ダートの実績平均RPCIが43.0と、芝の53.1から大きく乖離しているための専用閾値）。
  ヒーローの「想定展開」「読みやすい％」はこの判定結果（`forecast.pace_label`）を
  そのまま表示するだけなので、常に正しかった。
- フロントエンド`paceSpeedFromIndex()`（`apps/web/src/lib/pace.ts`）は、
  **トラック種別を区別しない固定閾値**（47/50/52/55、芝の分布に寄せた値）で
  数値を再分類していた。このレースの想定RPCIはダートとしては「平均」域（40〜46）
  だが芝基準の47は下回る値だったため、バックエンドは正しく「平均」、
  フロントは誤って「かなり速い流れ」と表示していた。
- `paceSpeedFromIndex()`は「詳細」タブの展開チェックリストだけでなく、展開予想
  ヒーロー（`PaceHeadline`）・確定後分析の各馬ペース傾向・PCI3表示など**7ファイル**で
  使われており、ダートレース全般で発生し得る不具合だった（芝はたまたま閾値が
  近いため目立たなかっただけ）。

### ユーザーとの合意事項

修正方針をAskUserQuestionで3案（3段階へ簡素化／5段階維持で芝・ダート別化／
今は直さず別途相談）提示し、**「3段階へ簡素化（推奨）」**を選択された。
新しい閾値は一切発明せず、バックエンドの既存閾値（芝49/51・ダート40/46）を
そのまま使う。

### 実施内容（`apps/web`）

- `lib/pace.ts`: `PaceSpeedLevel`を5段階
  （veryHigh/high/average/slow/verySlow/unknown）から3段階
  （high/average/slow/unknown）へ簡素化。`paceSpeedFromIndex(value, trackType)`が
  `trackType`を必須で受け取り、`trackType === "ダート"`ならダート専用閾値
  （40.0/46.0）、それ以外は芝閾値（49.0/51.0）を使うようバックエンドの
  `classify_pace()`と揃えた。`beginnerLabel`も「やや速い流れ」→「速い流れ」等、
  3段階に合わせて統一。未使用だった`paceSpeedLabel`/`paceSpeedSymbol`
  ラッパー関数は削除した。
- `forecastDecisionChecklist()`へ`trackType`パラメータを追加し、内部の
  `paceSpeedFromIndex()`呼び出しへ渡すようにした。
- 呼び出し元7ファイルすべてで`race.track_type`（または`RaceDetail`型の
  `track_type`）を明示的に渡すよう修正:
  `PaceHeadline.tsx`（`trackType`プロパティ追加）、`RaceForecastDashboard.tsx`、
  `MobileRaceForecastDashboard.tsx`、`RaceHero.tsx`、
  `MobilePaceAnalysisDashboard.tsx`（`MobilePaceResultRow`へ`trackType`
  プロパティ追加）、`PaceAnalysisTable.tsx`（`trackType`プロパティ追加）、
  `app/races/[raceKey]/pace-analysis/page.tsx`。
- `trackType`はオプション引数（バックエンドの`track_type: str = "芝"`と同じ
  既定値方式）にはせず、**必須引数**にした。将来新しい呼び出し箇所が
  `trackType`を渡し忘れて同じ不具合を再発することを防ぐため。

### 検証

- `pci=44・トラック=ダート`が「平均」、`pci=44・トラック=芝`が「ハイ」になる、
  という不具合の直接的な再現テストを`lib/pace.test.ts`の新規describeブロックへ
  追加（芝の3段階境界値・ダートの3段階境界値・両者の食い違い・未指定時の
  安全な縮退を含む計5件）。`PaceAnalysisTable.test.tsx`にも同じ再現テストを
  1件追加。
- Web 129 tests（新規9件、既存の5段階前提テストは3段階へ更新）、typecheck、
  production buildすべて成功。
- Playwrightでユーザー報告と同じダート1400m・想定RPCI=44のレースを再現し、
  ヒーローの「想定展開: 平均」表示に変化が無い（= 元々正しかった部分に
  回帰が無い）ことを確認した。詳細タブの展開チェックリストは静的レンダリング
  では非アクティブタブの内容がDOMに存在しないため画面上での目視確認はできず、
  `paceSpeedFromIndex(44, "ダート").label === "平均"`という単体テストでの
  直接検証で確認した（同じ関数を`forecastDecisionChecklist()`が呼ぶため、
  ロジックとしては確実に一致する）。

### 変更ファイル

1. `apps/web/src/lib/pace.ts`
2. `apps/web/src/lib/pace.test.ts`
3. `apps/web/src/components/PaceHeadline.tsx`
4. `apps/web/src/components/RaceForecastDashboard.tsx`
5. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
6. `apps/web/src/components/RaceHero.tsx`
7. `apps/web/src/components/MobilePaceAnalysisDashboard.tsx`
8. `apps/web/src/components/MobilePaceAnalysisDashboard.test.tsx`
9. `apps/web/src/components/PaceAnalysisTable.tsx`
10. `apps/web/src/components/PaceAnalysisTable.test.tsx`
11. `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`
12. `tasks/current.md`
13. `docs/HANDOFF.md`

新しい閾値・仕様は発明していない（バックエンドの既存`RuleWeights`をそのまま
フロントへ反映しただけ）ため`docs/DECISIONS.md`は更新していない。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/web/src/lib/pace.ts`
3. `apps/api/src/pci/domain/pace/rpci_forecast.py`（`classify_pace()`、閾値の正）

---

## 2026-07-26 (6) (Claude Code) 確定後分析にも馬番バッジの枠色を拡張（バックエンド対応）

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景

前タスク（馬番バッジ枠色統一）の末尾で「確定後分析のデスクトップ表
（`PaceAnalysisTable.tsx`）にも同じ不統一があるが、APIスキーマに`frame_no`が無いため
一段大きい変更になる」とユーザーへ確認を仰いだところ、「お願いします」と着手の
指示を受けたため、バックエンドから対応した。

### 実施内容（バックエンド、`apps/api`）

- `application/dto.py`: `HorsePaceAnalysisOutput`へ`frame_no: int`を追加
  （`horse_no`の直後、デフォルト値付きフィールドより前に配置）。
- `application/race_query_use_cases.py`: `GetPaceAnalysisUseCase.execute()`内の
  構築箇所へ`frame_no=e.frame_no`を追加（`RaceEntry.frame_no`は既存フィールドで
  マイグレーション不要）。
- `presentation/schemas.py`: `HorsePaceAnalysisSchema`へ`frame_no: int`を追加し、
  `PaceAnalysisSchema.from_dto()`のマッピングにも`frame_no=h.frame_no`を追加。
- `python scripts/export_openapi.py`でOpenAPIスペックを再生成
  （契約テスト`test_committed_openapi_is_in_sync`が期待どおり一度失敗→再生成後に合格）。
- `packages/api-client`で`npm run generate`を実行し`schema.d.ts`を再生成。
  `HorsePaceAnalysisSchema`に`frame_no: number`（必須）が反映されたことを確認。

### 実施内容（フロントエンド、`apps/web`）

- `PaceAnalysisTable.tsx`（確定後分析デスクトップ表）: `.horse-no.sm`固定黒地バッジを
  `frameColorClass(h.frame_no)`ベースへ変更。
- 併せて`MobilePaceAnalysisDashboard.tsx`の`MobilePaceResultRow`
  （スマホ確定後分析「全馬」タブ）も同じ不統一（`border-slate-200 bg-white`固定）を
  発見し、同様に`frameColorClass(horse.frame_no)`へ変更した
  （ユーザーの画面提示には無かったが、`HorsePaceAnalysis`型を使う同種の箇所のため
  今回のバックエンド変更で無償に直せると判断し、範囲に含めた）。
- `globals.css`の`.horse-no`/`.horse-no.sm`定義を削除した。前回のセッションで
  `HorseFitTable.tsx`の参照を外し、今回`PaceAnalysisTable.tsx`の参照も外したことで
  完全に未使用になったため（`grep`で参照ゼロを確認してから削除）。

### 検証

- API: `python -m pytest tests/unit/ tests/contract/ -q` 597 passed（+1）、
  ruff・mypy --strict（65ファイル）・lint-imports すべて成功。
- Web: `npm run test` 125 passed（+2 新規ファイル`PaceAnalysisTable.test.tsx`、
  既存`MobilePaceAnalysisDashboard.test.tsx`のアサーション強化）、typecheck、
  production buildすべて成功。
- Playwright（`renderToStaticMarkup`＋ビルド済みTailwind CSS）で、デスクトップ表
  （900px）とスマホ「全馬」行（390px想定）の両方を6頭のモックデータで確認し、
  枠色が正しく交互（白/黒/赤のペア）に表示され、横はみ出しが無いことを確認した。
  一時プレビューファイルは確認後に削除済み。

### 変更ファイル

1. `apps/api/src/pci/application/dto.py`
2. `apps/api/src/pci/application/race_query_use_cases.py`
3. `apps/api/src/pci/presentation/schemas.py`
4. `apps/api/tests/unit/application/test_pace_analysis_use_cases.py`
5. `apps/api/tests/contract/test_races_api.py`
6. `packages/api-client/openapi.json`（再生成）
7. `packages/api-client/src/schema.d.ts`（再生成）
8. `apps/web/src/components/PaceAnalysisTable.tsx`
9. `apps/web/src/components/PaceAnalysisTable.test.tsx`（新規）
10. `apps/web/src/components/MobilePaceAnalysisDashboard.tsx`
11. `apps/web/src/components/MobilePaceAnalysisDashboard.test.tsx`
12. `apps/web/src/app/globals.css`
13. `tasks/current.md`
14. `docs/HANDOFF.md`

新しい設計判断は発生していない（既存の`frameColorClass`をAPIスキーマ拡張の上で
展開しただけ）ため`docs/DECISIONS.md`は更新していない。これで馬番バッジの枠色は
出走前・確定後・デスクトップ・モバイルの全画面で統一された。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/api/src/pci/application/dto.py`
3. `apps/web/src/lib/pace.ts`

---

## 2026-07-26 (5) (Claude Code) 馬番バッジの枠色を全画面で統一

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景（ユーザーフィードバック）

ユーザーがスマホ実機の画面4枚（サマリータブの展開恩恵馬TOP3、注目馬タブの
展開恩恵馬TOP5、詳細タブの個別PAI根拠カード、および比較対象として隊列予想）を提示し、
「隊列予想では各馬番ごとに枠色が着色されているが、他の箇所では同様の色が塗られていな
かったり、表示形態が異なることがある。隊列予想のものと同じようにしてほしい」と
フィードバックした。

### 調査

`FormationView.tsx`に`FRAME_CLASS`（JRA公式8枠の配色をTailwindクラスで表現した
ローカル定数）が定義されており、`隊列予想`はこれを使って馬番バッジを枠色で描画していた。
一方、以下3箇所は同じ情報（`horse.frame_no`）を持ちながら未使用・不統一だった。

1. `MobileRaceForecastDashboard.tsx`の`BenefitRow`（サマリータブ・展開恩恵馬TOP3）:
   `border-current/15 bg-white/10`という、カードの背景色に応じた半透明バッジで
   枠色を反映していなかった。
2. 同ファイルの`MobileExpandableHorseRow`（注目馬タブ・展開恩恵馬TOP5／評価を下げたい馬）:
   `border-slate-200 bg-white text-slate-900`という常に同じ配色のバッジだった。
3. `HorseFitTable.tsx`（詳細タブの判断根拠データ、`globals.css`の`.horse-no`使用）:
   常に黒地（`#0f172a`固定）のバッジで、かつバッジ内テキストが`horseNumberLabel()`の
   フル文言（「馬番16」）で、隊列予想の「番号のみ」というフォーマットとも異なっていた。

なお`PaceAnalysisTable.tsx`（確定後分析のデスクトップ表、`.horse-no.sm`使用）にも
同じ不統一があるが、こちらが使う`HorsePaceAnalysisSchema`（API契約）には`frame_no`が
含まれておらず、バックエンドのdto/schema/OpenAPI再生成を伴う一段大きい変更になるため
**今回は対象外とし、ユーザーへの確認待ちとして残した**。

### 実施内容

- `apps/web/src/lib/pace.ts`へ`frameColorClass(frameNo: number): string`を追加した。
  JRA公式8枠の配色（1:白／2:黒／3:赤／4:青／5:黄／6:緑／7:橙／8:桃、
  `FormationView.tsx`の`FRAME_CLASS`と同じTailwindクラス文字列）を1箇所で管理し、
  `frame_no<=0`（枠順未確定）時は色を付けない中立クラス（`border-slate-200 bg-slate-100
  text-slate-400`）を返す。
- `FormationView.tsx`のローカル`FRAME_CLASS`定義を削除し、`frameColorClass()`を
  import して3箇所の呼び出しを置き換えた（挙動は変えず、定義を一本化しただけ）。
- `MobileRaceForecastDashboard.tsx`の`BenefitRow`・`MobileExpandableHorseRow`の
  馬番バッジを`frameColorClass(horse.frame_no)`へ変更した。
- `HorseFitTable.tsx`の馬番バッジ（`.horse-no`固定黒地）をTailwindの
  `frameColorClass(h.frame_no)`ベースへ変更し、バッジ内テキストも隊列予想と同じ
  「番号のみ」（未確定時は「登録」）へ変更した。「登録順N（馬番未確定）」という
  文言は、確定時（frame_no>0）は行内テキストから外し、未確定時だけ残した
  （確定時にも文言を付けるとPlaywrightでの390px確認で1行に収まらず不格好に
  折り返すことを確認したため、確定時はバッジのみで表現する設計にした）。
  `.horse-no`/`.horse-no.sm`のCSS定義自体は`PaceAnalysisTable.tsx`が引き続き使うため
  削除していない。

### 検証

- 新規9 tests: `lib/pace.test.ts`に`frameColorClass`の単体テスト4件
  （8枠それぞれ異なる配色・具体的な配色値・未確定時は中立・未定義枠番への安全な縮退）、
  `MobileRaceForecastDashboard.test.tsx`に1件追加（既存2件のアサーションも
  枠色チェックへ強化）、新規`HorseFitTable.test.tsx`2件。
- Web 123 tests、typecheck、production buildすべて成功。
- Playwright（`renderToStaticMarkup`＋ビルド済みTailwind CSS、`/opt/pw-browsers/chromium`）
  で18頭・複数枠のモックデータを使い、390px幅でサマリータブ（黒/緑/白の3種のカード背景）・
  注目馬タブ・詳細タブそれぞれのバッジが枠色で視認でき、横はみ出しが無いことを確認した。
  一時プレビューファイルは確認後に削除済み。

### 変更ファイル

1. `apps/web/src/lib/pace.ts`
2. `apps/web/src/lib/pace.test.ts`
3. `apps/web/src/components/FormationView.tsx`
4. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
5. `apps/web/src/components/MobileRaceForecastDashboard.test.tsx`
6. `apps/web/src/components/HorseFitTable.tsx`
7. `apps/web/src/components/HorseFitTable.test.tsx`（新規）
8. `tasks/current.md`
9. `docs/HANDOFF.md`

新しい設計判断・仕様変更は発生していないため（既存の`FRAME_CLASS`の値をそのまま
他画面へ展開しただけ）、`docs/DECISIONS.md`は更新していない。

### 未対応・ユーザー確認待ち

`PaceAnalysisTable.tsx`（確定後分析のデスクトップ表）も同じ枠色未対応だが、
`HorsePaceAnalysisSchema`に`frame_no`が無いため、対応するには
`HorsePaceAnalysisOutput`（dto.py）→`HorsePaceAnalysisSchema`（schemas.py）→
`GetPaceAnalysisUseCase`（`race_query_use_cases.py`、`RaceEntry.frame_no`は既存）→
OpenAPI再生成→api-client型再生成→フロント、という一段大きい変更が必要。
ユーザーの意向を確認してから着手する。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/web/src/lib/pace.ts`
3. `tasks/current.md`

---

## 2026-07-26 (4) (Claude Code) 開催日選択UIの改善（年表示・日付ストリップ絞り込み・月カレンダー展開）

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind

### 背景（ユーザーフィードバック）

ユーザーが実機でアプリを操作した後、JRA-VAN公式スマホアプリの画面2枚（メイン画面の
開催日チップ列、および「別日程で検索」押下後の年選択＋開催日一覧画面）を提示し、
「レース開催日を選ぶ方法がかなり煩わしい。特にスマホ版で、何年何月何日のレースか
わからない上、遡るためにたくさんスライドする必要がある」とフィードバックした。

### 原因調査

`apps/web/src/components/RaceDateCalendar.tsx`とデータ経路を確認し、2点を特定した。

1. スマホ版見出し（`MobileDateStrip`）と各日付チップが、月日と曜日のみを表示し
   **年を一切表示していなかった**（`7月26日（日）`のように）。
2. `GET /api/v1/races/dates`（`ListRaceDatesUseCase`）は「全開催日一覧」を無制限に返す
   設計で、フロント側もそれを丸ごと1本の横スクロール帯（`MobileDateStrip`）に並べていた。
   開催日が半年〜1年分蓄積していれば、遡るほど並ぶチップ数が増え続け、スライド量が
   際限なく増える構造だった。JRA-VANの参考画像は直近6件程度のチップ＋「別日程で検索」
   （年選択＋開催日一覧表の別画面）という2段構えで、近傍と遠方を明確に分離していた。

### ユーザーとの合意事項

「遠い日付へのジャンプ手段」の実装方針についてAskUserQuestionで3案
（PC版月カレンダー流用／JRA-VAN風専用画面新設／年月ドロップダウンのみ追加）を提示し、
**「既存のPC版月カレンダーを流用」**（新規ページ・新規API不要、低リスク）を選択された。

### 実施内容（`apps/web/src/components/RaceDateCalendar.tsx`）

- スマホ見出しへ年を追加: `${active.getFullYear()}年${...}月${...}日（${...}）`。
- `STRIP_WINDOW_BEFORE=4`/`STRIP_WINDOW_AFTER=1`を新設し、`MobileDateStrip`が
  `availableDates`全件ではなく、選択中の日付を基準に「前4件＋本人＋後1件（最大6件）」だけを
  スライスして表示するように変更（`activeIndex`を`availableDates.indexOf(activeDate)`で求め、
  `slice(windowStart, windowEnd)`で切り出す。配列境界は`Math.max`/`Math.min`で自然にクランプ）。
- ストリップの下（`md:hidden`領域）に「他の日程を探す」トグルボタンを追加。
  `useState`の`showPicker`で開閉し、開くと既存のPC版月カレンダー（開催日ドット付き、
  `calendarDays()`のグリッド）を**インラインで展開表示**する。従来はこのカレンダー全体が
  `hidden ... md:block`でスマホでは常に非表示だった。トグルボタン自体はスクロール外の
  常時表示要素とし（JRA-VANのようにチップ列の中に埋め込むと、選択日センタリングで
  スクロールされた際に押しにくくなるため、意図的に列の外に配置した）。
- 月カレンダーの年月ナビ行へ、`ChevronsLeft`/`ChevronsRight`（前年/翌年）を
  既存の`ChevronLeft`/`ChevronRight`（前月/翌月）の外側に追加。半年以上前の日付へは
  月送りのみだと同様に大量クリックが必要になるため。

### 未確定のまま残した点

- ストリップの窓幅（前4件＋後1件＝最大6件）はJRA-VANの参考画像の見た目（6チップ）に
  合わせた値で、実データでの使用感検証はしていない。将来「まだ少し多い/少ない」と
  感じた場合は`STRIP_WINDOW_BEFORE`/`STRIP_WINDOW_AFTER`の定数だけを調整すればよい。
- 月カレンダー展開時、日付を選択した後にトグルを自動で閉じる仕様にはしていない
  （選択後も同じ月内で別日を続けて選べるよう、意図的に開いたままにした）。

### 変更ファイル

1. `apps/web/src/components/RaceDateCalendar.tsx`
2. `apps/web/src/components/RaceDateCalendar.test.tsx`（新規3 tests追加、既存2 tests更新）
3. `tasks/current.md`
4. `docs/HANDOFF.md`

新しい設計判断のうち「PC版カレンダー流用」はユーザーとのAskUserQuestionで確定済みのため、
`docs/DECISIONS.md`への追記は不要と判断した（軽微なUI実装方針であり、ADR相当の
「後で覆すと高コストな決定」には該当しない）。

### テスト実行コマンドと結果

```bash
cd apps/web && npm run test        # 116 passed（+3、既存2件更新）
npm run typecheck                  # 成功
npm run build                      # 成功（/ First Load JS 117kB）
```

Playwright（`renderToStaticMarkup`＋ビルド済みTailwind CSS、`/opt/pw-browsers/chromium`）で
390px幅の折りたたみ・展開（`hidden`クラスをDOM操作で外して疑似再現）両状態と、
実際のデスクトップサイドバー幅である272px（`page.tsx`の`grid-cols-[272px_...]`）を
スクリーンショット確認。3状態とも`scrollWidth===clientWidth`一致（横はみ出し無し）、
年月ナビ行の折り返し・クロップも無いことを確認した。一時プレビューファイルは確認後に削除済み。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `apps/web/src/components/RaceDateCalendar.tsx`
3. `tasks/current.md`

---

## 2026-07-26 (3) (Claude Code) 実端末ロケテストの準備確認

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind
- **このセッションはコード変更なし、ドキュメントのみ更新**

### 背景

前回セッションで「①スマホ主要導線の通し確認」が完了し、残る「②実端末ロケテスト」
「③モバイルアクセシビリティ確認」は実機必須のため着手できなかった。ユーザーへ
次の一手を確認したところ「実機ロケテストの準備確認」を選択されたため、実行自体は
ユーザーの実機へ委ね、準備（スクリプトの整合性確認＋実機で使えるチェックリスト作成）
だけをこのセッションで行った。

### 実施内容

1. **Quick Tunnelスクリプトの整合性確認**: `apps/web/scripts/run_location_test_tunnel.ps1`を
   読み直し、直近のモバイルUI変更（`IngestStatusBanner`のモバイル要約化等）と衝突しないか
   確認した。スクリプトは認証（Basic/Bearer）・トンネル起動・readinessの検証のみを行い、
   画面内容への依存は「レースボード」という文字列の存在と、既知のエラー文言
   （「レース一覧を取得できませんでした」「APIに接続できませんでした」）の不在確認だけ
   だったため、モバイル固有の変更による更新は不要と判断した。
2. **実装済みのアクセシビリティ/タップ領域の棚卸し**: 対象5コンポーネント
   （`RaceDateCalendar`・`MobileRaceGroupedSection`・`MobileRaceNavigation`・
   `MobileRaceForecastDashboard`・`MobilePaceAnalysisDashboard`）のソースを読み、
   `aria-current`（日付ストリップ="date"、同一開催ナビ="page"）、
   `role="tablist"`/`role="tab"`/`aria-selected`（競馬場タブ・詳細タブ）、
   44px相当のタップ領域（`h-11`/`w-11`=44px、日付ストリップは`h-14 min-w-14`=56px）の
   実装状況を具体的に確認した。
3. **既知の制約を1点発見**: 詳細タブ（出走前4タブ・確定後3タブ）はどちらも
   アクティブな1パネルだけをDOMへ描画する実装のため、非アクティブなタブボタンの
   `aria-controls`が、その時点でDOM上に存在しないパネルIDを参照する
   （例: `mobile-panel-formation`は`summary`タブ表示中は未マウント）。
   スクリーンリーダーや自動監査ツール（axe等）が警告を出す可能性があるが、
   実際の読み上げが破綻していなければ実害はないと判断し、**コードは変更していない**
   （「実機で問題が確認されてから対応する」という本プロジェクトの既存の合意方針
   ―④日付ストリップDOM削減が実機性能問題の確認待ちであるのと同じ考え方―に揃えた）。
4. **チェックリストの作成**: 上記を`docs/LOCATION_TEST.md`§10
   「開発者によるモバイル実機QA（横はみ出し・タップ領域・アクセシビリティ）」として
   新規追加した。対象画面（トップ→同一開催ナビ→出走前4タブ→確定後3タブ）、
   表示幅の目安（320/375/390/430px）、A横はみ出し／B タップ領域／Cスクロール位置／
   Dキーボード操作／E aria-current・読み上げ順の5観点、既知の制約、記録方法を整理した。
   第7節（参加者向けUXアンケート）とは別物であることを明記した。

### 変更ファイル

1. `docs/LOCATION_TEST.md`（§10新規追加）
2. `tasks/current.md`（②③へ準備完了の参照を追加、チェックボックスは未実施のまま維持）
3. `docs/HANDOFF.md`

コード変更・新しい設計判断は無いため、ソースファイルと`docs/DECISIONS.md`は
変更していない。

### 未実施（範囲外・実機が必要）

- 実際のiOS Safari/Android Chromeでの横はみ出し・タップ領域・スクロール位置確認
- VoiceOver/TalkBackでの読み上げ確認
- 友人からの指摘収集
- 上記チェックリストに基づく実機QAの実行そのもの

### テスト実行コマンドと結果

ドキュメントのみの変更のため、テスト再実行は行っていない
（直前セッションのWeb 113 passedから変更なし）。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `docs/LOCATION_TEST.md`§10
3. `tasks/current.md`

---

## 2026-07-26 (2) (Claude Code) スマホ主要導線の通し確認（静的レンダリング範囲）

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時点: origin/HEADと0 ahead/0 behind（前回セッションから新規コミットなし）
- 最新コミット: 変更なし（**このセッションはコード変更なし、ドキュメントのみ更新**）

### 実施内容

`tasks/current.md`の検証タスク「P2 スマホ主要導線の通し確認」に着手した。

- **環境確認**: このクラウド環境ではDocker daemonを起動できない
  （`service docker start`が`ulimit: error setting limit (Operation not permitted)`で失敗、
  非特権サンドボックスの制約）。実DB接続の開発サーバーでのクリック通し確認は不可と確認した。
- **代替手法**: 主要導線を構成する各モバイルコンポーネント（`RaceDateCalendar`・
  `MobileRaceGroupedSection`・`MobileRaceNavigation`・`MobileRaceForecastDashboard`・
  `MobilePaceAnalysisDashboard`）を、既存`*.test.tsx`のfixtureを土台にした現実的な
  モックデータで`renderToStaticMarkup`し、ビルド済みTailwind CSS（`.next/static/css/*.css`）を
  適用した静的プレビューをPlaywright（`/opt/pw-browsers/chromium`）で390px幅スクリーンショット。
  生成に使った一時テストファイル（`src/components/ZPreviewFlow.test.tsx`）は確認後に削除済み
  （`git status`で残存無しを確認）。
- **確認した導線**: レースボード（日付ストリップ→競馬場タブ→レース行）→同一開催ナビ→
  レース詳細（ヒーロー→サマリータブ：展開恩恵馬TOP3・評価を下げたい馬・一覧へ戻るリンク）→
  確定後分析（ヒーロー→サマリータブ：上位3頭・ひとこと振り返り）。
- **機械的な横はみ出しチェック**: `document.documentElement.scrollWidth`と`clientWidth`が
  ともに390で一致することをPlaywright上で確認（横スクロールが発生していない）。
- **見かけ上の異常2点を調査し、いずれも自分のモックデータの不備と特定**（実装側の不具合ではない）:
  1. レース行の展開ラベルが「判断材料が不足」と表示 → `beginnerPaceLabel()`
     （`lib/pace.ts`）は「ハイ/平均/スロー」の3値のみを認識する設計で、モックに
     独自の説明文字列を渡していたのが原因。正しい値で再現すると想定どおり表示された。
  2. 確定後分析の「実際の流れ」バッジに`H`、各馬結果に`M`という文字 →
     `PACE_SPEED_META`（`lib/pace.ts`）が持つ意図的な短縮記号（`symbol`フィールド）で、
     常にフルの日本語ラベル（例:「Hハイ」＝symbol"H"+label"ハイ"）と併記される既存仕様。
     内部の実数値露出ではなく`docs/PROJECT_RULES.md §5`の違反ではない。
- **見つかった実装上の不具合は無し**。デフォルト表示（初期タブ）の範囲で、全パネルが
  390px幅に収まり、テキストの意図しない欠けや崩れも無かった。

### 未実施（範囲外・実機/実DBが必要）

- 4タブ（サマリー/隊列/注目馬/詳細）の実際のクリック切り替え動作
  （静的SSRレンダリングのため初期タブしか確認できていない。クライアント側JSでの
  切り替えは今回検証していない）。
- 実スクロール挙動、iOS Safari/Android Chrome実機、キーボード操作・スクリーンリーダー確認。
  → `tasks/current.md`の「実端末ロケテスト」「モバイルアクセシビリティ確認」へ引き続き委ねる。

### 変更ファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`

コード変更・新しい設計判断は無いため、ソースファイルと`docs/DECISIONS.md`はいずれも
変更していない。

### テスト実行コマンドと結果

```bash
cd apps/web && npm run test   # 113 passed（変更なし。確認作業のみのため）
```

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `tasks/current.md`

### Codexが最初に実行するコマンド

```bash
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -5
git status   # クリーンであるはず（このセッションはコード変更なし）
```

---

## 2026-07-26 (Claude Code) Codex引き継ぎ検証＋取り込み警告のモバイル要約化

- 作業担当: Claude Code
- 引き継ぎ先: OpenAI Codex
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始時のローカルHEAD: `d2a74ff`（自分の前回セッションの最終コミット）
- 作業開始時点でorigin: `d751bf8`（**117コミット先行**。`git pull --ff-only`で安全に追従）
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）

### Codex引き継ぎの検証結果（コード変更前に実施）

ユーザー指示により、実装前にCodexの117コミット分の作業を検証した。

- **Git確認**: ローカルはorigin/claude/sweet-einstein-ilnaovより117コミット遅れていた
  （0 ahead / 117 behind、working tree clean）。履歴を書き換えず`git pull --ff-only`で
  fast-forward追従（安全: ローカルに独自コミットが無かったため）。
- **完了内容の概要**（詳細はHANDOFF.md内の各日時セクション・`docs/DECISIONS.md`参照）:
  RPCI予測モデルのv1→v4反復改善（各候補は必ず本番と独立期間比較し、改善しない場合は
  正直に不採用として記録）、ability-v3/PAI course-aptitude、S3/L3内部永続化、
  重複レースキーの安全な統合（dry-run既定・署名検証付き削除ガード）、Windows取り込みの
  堅牢化（文字化け修正・readiness事前確認・Webhook集約秘匿）、モバイルUI全面改修、
  限定ロケテスト基盤（Basic/Bearer認証・Cloudflare Quick Tunnel・公開前HTTP点検CLI）。
- **テスト再実行**（このクラウド環境、Codexの記載件数と照合）: API 596 passed、
  ingestion-worker 239 passed、Web 111 passed（新規追加前）。いずれもCodex記載と完全一致。
  ruff/lint-imports/mypy --strict（API）/typecheck/build/OpenAPI同期/Alembicチェーン
  （001→006単線）もすべて確認しclean。
- **唯一の見かけ上の不一致（原因特定済み・対応不要）**: `python -m mypy src/ --strict`を
  素の設定でこのLinux環境で実行すると`windows_client.py`で3件（`_software_id`/`_race_option`
  の型を決定できない）エラーが出て、「ingestion-worker全体のRuff・mypy違反を解消した」という
  記載と食い違うように見えた。原因は`if sys.platform != "win32": raise ...`というOS分岐を、
  mypyがこの環境（Linux）のデフォルトプラットフォーム前提で解析し、以降の属性代入を
  「到達不能コード」とみなして型を見失うという**mypyの`--platform`依存の環境差**。
  `mypy --strict --platform win32`で実行すると24ファイル全体で0エラーになることを確認した。
  Windows実行機（本番の実行環境）では自然に発生しない。**コードの不具合ではないため
  対応不要**と判断し記録のみ残す。
- 新規に監査したポイント: 新規認証コード（`middleware.ts`/`betaAccess.ts`）は定数時間比較・
  設定不備時fail-closedで健全。重複レース統合スクリプト（`reconcile_duplicate_races.py`）は
  既定dry-run・`--apply`必須・署名検証付き削除ガードで安全設計。新規コンポーネントの
  `predicted_rpci`/`rpci_actual`等はすべて`paceSpeedFromIndex()`翻訳層経由で、UIへの
  実数値露出なし（`docs/PROJECT_RULES.md §5`順守を確認）。
- **重大な不整合はなし**と判断し、`tasks/current.md`最優先未完了タスクへ進んだ。

### 今回完了した内容（取り込み警告のモバイル要約化、P1確定タスク）

- `IngestStatusBanner.tsx`へ768px未満専用の要約行（アイコン(h-6 w-6)＋見出しのみ・
  `truncate`付き1行、`md:hidden`）を追加した。768px以上は既存の見出し＋detail文の
  2段表示（`hidden items-start gap-3 md:flex`）を維持する。外側のpaddingは
  `p-3 md:p-4`とし、モバイルでの余白も詰めた。
- 詳細（失敗一覧・成績未取込・馬場情報未反映・重複レース・復旧コマンド）を格納する
  `<details>`は構造・内容とも変更していない（既存の折りたたみのまま両breakpointで表示）。
- **最優先状態の選定順は独自に決めていない**: `ingestStatusMeta()`は既にif/else-ifの
  優先度カスケード（失敗＞成績未取込＞馬場情報未反映＞重複レース＞鮮度低下＞正常）で
  単一の`headline`/`tone`へ絞り込み済みのため、モバイル要約はその`meta.headline`を
  そのまま使うだけで新しい優先順位判断は発生しない。件数も既存のheadline文字列に
  埋め込み済みの値をそのまま使い、複数カテゴリを横断合算する新しい集計は行っていない
  （その集計方法自体は前回セッションが「未確定」として残した論点で、今回も未確定のまま）。
- `IngestStatusBanner.test.tsx`に2件追加（既存2件は無変更）:
  「モバイル専用の要約行に見出しを常時表示し、detail文は含めない」
  「PC表示（md:）は見出し・detail文とも従来どおり維持する」。
- Playwright（`/opt/pw-browsers/chromium`）で実際にレンダリングした静的プレビュー
  （`renderToStaticMarkup`＋ビルド済みTailwind CSS）を390px・1024pxでスクリーンショットし、
  390pxで警告/正常/失敗の3状態とも1行に収まり横はみ出しが無いこと、1024pxで従来の
  見出し＋detail文の2段表示が保たれることを目視確認した（一時ファイルは確認後に削除）。

### 変更ファイル

1. `apps/web/src/components/IngestStatusBanner.tsx`
2. `apps/web/src/components/IngestStatusBanner.test.tsx`
3. `tasks/current.md`
4. `docs/HANDOFF.md`

新しい設計判断・仕様変更は発生していないため`docs/DECISIONS.md`は更新していない
（`ingestStatusMeta()`のロジックは無変更、既存の優先順位をそのまま流用したため）。

### テスト実行コマンドと結果

```bash
cd apps/web
npm run test          # 113 passed（16 files、+2）
npm run typecheck     # 成功
npm run build         # 成功（5ページ）
```

lint: 引き続き`apps/web/package.json`に`lint`スクリプトが無く実行不可（既知・Codex記載どおり）。

### 未完了・次に実施する具体的な手順

- **P2（未実施）**: 390px等での主要導線通し確認、iOS Safari/Android Chrome実機確認、
  アクセシビリティ確認（`tasks/current.md`「検証タスク」参照）。
- **P3（条件付き）**: 日付ストリップのDOM削減。実機で性能問題が出るまで着手しない。
- **未確定のまま**: モバイル警告で複数カテゴリが同時に該当する場合の「合算件数」の
  集計方法（`ingestStatusMeta()`は現状1カテゴリしか同時に返さない設計のため、
  合算が必要かどうか自体を含めユーザー確認が必要）。
- **条件待ち**: 予想照合30件到達時の初回レビュー、ダート確定100件+ハイ20件到達時の
  RPCI v4監視レビュー（いずれも閾値未到達、`tasks/current.md`参照）。

### Codexが最初に確認するファイル

1. `docs/HANDOFF.md`（本節）
2. `tasks/current.md`
3. `apps/web/src/components/IngestStatusBanner.tsx`
4. `apps/web/src/components/IngestStatusBanner.test.tsx`

### Codexが最初に実行するコマンド

```bash
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -5
git status   # クリーンであるはず
cd apps/web && npm run test && npm run typecheck && npm run build
```

---

## 2026-07-26 01:31 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- 現在のブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `b6c9c06`
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）
- 今回の作業目的: 新規実装を開始せず、直前のスマホUI改善とGit状態を再検証し、
  Claude Codeが資料と実コードだけから安全に再開できる状態へ整理する。

### 完了した内容

- 引き継ぎ整理開始時にworking treeがクリーンで、未追跡・ステージ済み・未コミット変更が
  ないことを確認した。
- 最新機能コミット`94a6f0e feat(web): compact mobile race calendar`を自己レビューした。
- `RaceDateCalendar.tsx`、`RaceDateCalendar.test.tsx`、`page.tsx`に
  `console.log`、`debugger`、TODO、FIXME、一時コードがないことを確認した。
- Web全テスト、型チェック、本番ビルドを再実行した。
- Web lintを実行し、`apps/web/package.json`に`lint`スクリプトがないため
  lint処理を開始できないことを確認した。
- 前回の実機確認用Cloudflare Quick Tunnelを停止した。
- 新しい仕様・設計判断はないため、`docs/DECISIONS.md`と`docs/SPEC.md`は変更していない。

### 未完了の内容

- P1「取り込み警告のモバイル要約化」は未着手。
- 390pxの主要導線通し確認、320px・375px・430px確認、iOS Safari・Android Chrome実端末確認は未実施。
- 日付ストリップのDOM削減は、実端末で性能問題を確認した場合だけ着手する条件付きタスク。

### 作業が止まっている箇所

- `apps/web/src/components/IngestStatusBanner.tsx`の`IngestStatusBanner`を読み終えた段階。
- 現状は警告詳細全体が1つの`details`へ格納済みだが、モバイルでは見出し、
  `meta.detail`、余白が常時表示される。モバイル用の短い要約表示は未実装。
- 要約で常時表示する「最優先状態」の選定順は未確定。
  `ingestStatusMeta()`の既存優先順位から一意に判断できない場合は独断で決めない。

### 次に実施する具体的な手順

1. `apps/web/src/lib/ingestStatus.ts`の`ingestStatusMeta()`を確認し、既存のheadline、
   detail、tone、件数の生成順を把握する。
2. `apps/web/src/components/IngestStatusBanner.tsx`の`IngestStatusBanner`へ
   768px未満専用の要約を追加する。件数・状態は常時表示し、対象レース一覧と
   `IngestRecoveryCommand`は既存の`details`内に維持する。768px以上は現行表示を変えない。
3. `apps/web/src/components/IngestStatusBanner.test.tsx`の
   「警告の詳細と復旧手順を1つの折りたたみにまとめる」と
   「正常時は不要な詳細開閉を表示しない」を維持し、モバイル要約と
   PC表示維持のテストを追加する。その後、Web全テスト、型チェック、本番ビルドと
   390pxブラウザ確認を行う。

### 対象ファイル

1. `apps/web/src/components/IngestStatusBanner.tsx`
2. `apps/web/src/components/IngestStatusBanner.test.tsx`
3. `apps/web/src/lib/ingestStatus.ts`
4. `tasks/current.md`
5. `docs/HANDOFF.md`
6. 設計判断が生じた場合のみ`docs/DECISIONS.md`

### 仮実装・暫定値

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 日付ストリップは56px幅のセルで、期間内の全開催日をDOMへ保持する。
- 警告詳細は現行どおり初期状態を閉じ、開閉状態を利用者ごとに保存しない。

### 未確定仕様

- モバイル警告で複数異常が同時発生した場合の「最優先状態」の選定順。
- 警告要約へ表示する件数を合計件数にするか、異常種別ごとの件数にするか。
- 320px・375px・430pxおよび実端末で許容するバナー初期高さ。

### 既知の不具合

- `apps/web/package.json`に`lint`スクリプトとESLint依存がなく、Web lintを実行できない。
- Next.jsビルドも`Skipping linting`となり、lintの代替にはならない。
- Codexの制限付きサンドボックスではVitest/esbuildが親ディレクトリを走査して
  `Access is denied`になる場合がある。通常のローカル権限では111件すべて成功する。
- Cloudflare Quick Tunnelは停止済み。次回の実機確認では
  `apps/web/scripts/run_location_test_tunnel.ps1`を再実行し、新しいURLを取得する必要がある。

### テスト実行コマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run lint --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

### テスト結果

```text
Web test: 16 files / 111 tests passed
Web typecheck: passed
Web lint: 実行不可（Missing script: "lint"）
Web production build: passed
Next.js build: compiled successfully / type validation passed / 3 static pages generated
```

### Claude Codeが最初に確認するファイル

1. `docs/HANDOFF.md`
2. `tasks/current.md`
3. `apps/web/src/components/IngestStatusBanner.tsx`
4. `apps/web/src/components/IngestStatusBanner.test.tsx`
5. `apps/web/src/lib/ingestStatus.ts`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull --ff-only origin claude/sweet-einstein-ilnaov
git status --short
git log -1 --oneline
npm.cmd test --workspace=@pci/web
```

## 2026-07-26 01:27 JST Codex向け引き継ぎ整理

- 引き継ぎ整理担当: OpenAI Codex
- 引き継ぎ先: OpenAI Codex（次タスク）
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `94a6f0e`
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）
- 目的: 新規実装を行わず、直前のスマホ開催日カレンダー改善を検証し、
  次の担当がGitと資料だけから安全に再開できる状態へ整理する。

### Git差分の確認

- 引き継ぎ整理開始時のworking treeはクリーンだった。
- 最新の機能コミットは`94a6f0e feat(web): compact mobile race calendar`。
- 直前の機能差分は`RaceDateCalendar`のモバイル日付ストリップ、テスト、
  `page.tsx`のモバイル幅制約、および関連資料だけである。
- 未追跡ファイル、ステージ済み差分、未コミットの機能変更はなかった。

### 今回完了した内容

- `CLAUDE.md`の作業中断・終了手順を確認した。
- Web全テストと型チェックを最新コミット上で再実行した。
- Web lintを実行し、スクリプト未定義で開始できないことを再確認した。
- `tasks/current.md`へスマホ画面向け残タスクを優先度・確定度別に整理した。
- 新しい設計判断や仕様変更はないため、`docs/DECISIONS.md`と`docs/SPEC.md`は変更していない。

### 変更ファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`

### テスト実行コマンドと結果

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run lint --workspace=@pci/web
```

```text
Web: 16 files / 111 tests passed
Web typecheck: passed
Web lint: failed before lint開始（Missing script: "lint"）
Sandbox内の初回Vitest: 親ディレクトリ読取制限で起動前に失敗
通常のローカル権限での同一Vitest: 111 tests passed
```

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 日付ストリップは56px幅のセルとし、期間内の全開催日をDOMへ保持する。
- 日付DOMの絞り込み・仮想化は未採用。実端末で性能問題を確認した場合だけ設計する。
- 取り込み警告の要約で常時表示する「最優先状態」の選定順は未確定。
  既存データを削らず、現行の警告優先度から判断できない場合は仕様確認を行う。
- 320px・375px・430px、iOS Safari、Android Chromeでの通し確認は未実施。

### 既知の問題

- `apps/web/package.json`に`lint`スクリプトとESLint依存がなく、Web lintを実行できない。
- Codexの制限付きサンドボックスではVitest/esbuildが親ディレクトリを走査して
  `Access is denied`になる場合がある。通常のローカル権限では再現せず全テストが通る。
- Cloudflare Quick Tunnelは一時URLであり、実行ターミナルの終了や再起動でURLが変わる。

### スマホ画面向け残タスク

1. P1: `IngestStatusBanner.tsx`のモバイル要約化とコンポーネントテスト更新。
2. P2: 主要導線の390px通し確認、iOS/Android実端末確認、アクセシビリティ確認。
3. P3: 日付ストリップの性能問題が実測された場合だけDOM削減を検討。

### Codexが最初に行う作業

1. `git status --short`と`git log -1 --oneline`を実行し、本節のコミットとcleanなworking treeを確認する。
2. `apps/web/src/components/IngestStatusBanner.tsx`と
   `apps/web/src/components/IngestStatusBanner.test.tsx`を読み、既存警告の優先順位と開閉構造を確認する。
3. P1の作業範囲を「モバイル要約・PC維持・テスト・390px確認」に限定して実装し、
   `npm.cmd test --workspace=@pci/web`と`npm.cmd run typecheck --workspace=@pci/web`を実行する。

## 2026-07-26 01:19 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `2c71441`
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）
- 目的: スマホの月間開催日カレンダーを日付ストリップへ圧縮し、レース一覧へ早く到達できるようにする。

### 完了内容

- `RaceDateCalendar`へ768px未満専用の`MobileDateStrip`を追加した。
- レースが存在する開催日だけを曜日・月日の2段表示で横一列に並べた。
- 選択日を中央へ自動スクロールし、前後の開催日へ移動できるようにした。
- 日付リンクへ`performance_days`を引き継ぎ、検証期間の選択を維持した。
- モバイル側の幅制約を追加し、長期間の日付があってもページ全体が横へ広がらないようにした。
- 768px以上は既存の月間カレンダーを維持した。

### 変更ファイル

1. `apps/web/src/components/RaceDateCalendar.tsx`
2. `apps/web/src/components/RaceDateCalendar.test.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`
5. `docs/DECISIONS.md`
6. `docs/HANDOFF.md`

### テスト結果

```text
Web: 111 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当: calendar height 149 / first race list top 845 / horizontal overflowなし
選択日中央寄せ: strip center 184 / selected center 184 / delta 0
日付切替: 7月25日から7月26日へ遷移し、performance_days=90の維持を確認
1440px相当: mobile calendar 0 / desktop monthly calendar 1 / horizontal overflowなし
```

### 未完了・次の具体的作業

- 次のスマホ優先改善は、取り込み警告を要約表示へ圧縮する。
- `apps/web/src/components/IngestStatusBanner.tsx`のモバイル表示で、警告タイトル・件数・
  最優先状態だけを常時表示し、対象レース一覧と再同期・補完コマンドを`details`へ移す。
- 768px以上の表示は維持し、390px相当で警告あり・警告なし・詳細展開、
  キーボード操作、横はみ出しを検証する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 各日付セルは56px幅とし、選択日は中央へ配置する。
- 期間内の全開催日をDOMへ保持する。端末性能への影響が確認された場合は仮想化または
  前後期間の絞り込みを検討する。

### 既知の不具合

- `apps/web/package.json`にlintスクリプトがなく、Web lintは単独実行できない。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/RaceDateCalendar.tsx`
2. `apps/web/src/components/RaceDateCalendar.test.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-26 01:05 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `4e06580`
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）
- 目的: スマホのレースボード上部を圧縮し、開催日とレース一覧へ早く到達できるようにする。

### 完了内容

- 4統計カードをスマホでは高さ74pxの4列サマリーへ統合した。
- 同じ件数を重複表示していたスマホのレース一覧フィルターを非表示にした。
- `ForecastPerformanceSummary`をスマホでは初期高さ66pxの`details`サマリーに変更した。
- 閉じた状態でも対象期間、全体一致状況、検証件数、カバー率を確認できる。
- 展開後は30・90・180日切替、カバー率、全体・芝・ダート集計、
  信頼度別集計、推移、不一致傾向、直近不一致を従来どおり確認できる。
- 768px以上は従来の4カードと予想検証の連続表示を維持した。

### 変更ファイル

1. `apps/web/src/app/page.tsx`
2. `apps/web/src/components/ForecastPerformanceSummary.tsx`
3. `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
4. `tasks/current.md`
5. `docs/DECISIONS.md`
6. `docs/HANDOFF.md`

### テスト結果

```text
Web: 109 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当: stats height 74 / closed performance height 66 / first race list top 1112
詳細展開後: performance height 337 / period nav 1 / coverage progress 1
1440px相当: mobile summary 0 / desktop filters and performance visible / horizontal overflowなし
```

### 未完了・次の具体的作業

- 次のスマホ優先改善は、月間開催日カレンダーを横スクロールの日付ストリップへ圧縮する。
- `apps/web/src/components/RaceDateCalendar.tsx`にモバイル表示を追加し、
  選択日を中央へ寄せ、開催日のみを前後へ移動できるようにする。
- PCの月間カレンダーは維持し、390px相当で選択日、前後開催日、横はみ出し、
  最初のレース一覧位置を検証する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 予想検証は初期状態を閉じる。利用者ごとの開閉状態は保存しない。
- 統計ラベルは「今週末・出走前・確定後・開催場」の4項目で固定する。

### 既知の不具合

- `apps/web/package.json`にlintスクリプトがなく、Web lintは単独実行できない。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`
2. `apps/web/src/components/ForecastPerformanceSummary.test.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-26 00:50 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `f65c6bf`
- 最新コミット: 本節と同じコミット（`git log -1 --oneline`で確認）
- 目的: スマホのレース一覧を競馬場タブと短いレース行へ再構成し、開催日の縦スクロールを短縮する。

### 完了内容

- `MobileRaceGroupedSection`を追加し、768px未満では開催日ごとに競馬場タブを表示するようにした。
- 選択中の競馬場だけを表示し、札幌・新潟・中京などを44px以上のタブで切り替えられる。
- 各レースをレース番号、レース名、芝・ダートと距離、頭数、初心者向け展開ラベル中心の
  コンパクト行へ変更した。
- 注目・妙味ラベルは一覧に残し、候補馬や推奨理由などはレース詳細画面へ集約した。
- 768px以上は従来の3開催場横並びと詳細カードを維持した。
- 390px相当の7月25日で3競馬場の切替、選択中の新潟12R、横はみ出しなしを確認した。

### 変更ファイル

1. `apps/web/src/components/MobileRaceGroupedSection.tsx`
2. `apps/web/src/components/MobileRaceGroupedSection.test.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`
5. `docs/DECISIONS.md`
6. `docs/HANDOFF.md`

### テスト結果

```text
Web: 107 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当: venue tabs 3 / selected venue 新潟 / visible rows 12 / horizontal overflowなし
1440px相当: visible mobile lists 0 / desktop race links visible / horizontal overflowなし
```

### 未完了・次の具体的作業

- 次のスマホ優先改善は、トップの4統計カードと`ForecastPerformanceSummary`を圧縮し、
  開催日カレンダーとレース一覧へより早く到達できるようにする。
- 実装時は`apps/web/src/app/page.tsx`の`StatTile`と
  `apps/web/src/components/ForecastPerformanceSummary.tsx`を確認する。
- 390px相当で初期表示から最初のレース一覧までの距離、横はみ出し、PC表示の維持を検証する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- タブの初期選択はAPIの開催場順の先頭。利用者ごとの選択記憶は未実装。
- モバイル行は最小64px。候補馬と推奨理由を一覧へ再掲する要件は未確定。

### 既知の不具合

- `apps/web/package.json`にlintスクリプトがなく、Web lintは単独実行できない。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobileRaceGroupedSection.tsx`
2. `apps/web/src/components/MobileRaceGroupedSection.test.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 14:25 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `2df91a3`
- 目的: スマホの隊列予想を短くし、全馬の配置を一度に把握できるようにする。

### 完了内容

- `MobileFormationBoard`を追加し、先頭・好位・中団・後方を4列で同時表示するようにした。
- 各馬は枠色付き馬番と省略可能な馬名だけの48pxチップへ圧縮した。
- 初期状態では各馬の理由文を表示せず、選択した1頭だけ脚質、信頼度、配置理由を
  ボード下へ展開する。
- 同じ馬を再度選ぶと詳細を閉じ、別の馬を選ぶと詳細を1件だけ切り替える。
- 768px以上は従来の馬名、脚質、信頼度、理由を含む4列カードを維持した。
- 390px相当の新潟11R・18頭で、ボード高454px、隊列パネル高514px、
  ページ高990px、ページ横はみ出しなしを確認した。
- ノーブルラホーヤを選択し、詳細1件、選択状態1件、理由表示を確認した。

### 変更ファイル

1. `apps/web/src/components/FormationView.tsx`
2. `apps/web/src/components/FormationView.test.tsx`
3. `tasks/current.md`
4. `docs/DECISIONS.md`
5. `docs/HANDOFF.md`

### テスト結果

```text
Web: 105 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当: visible horses 18 / board height 454 / panel height 514 / page height 990
馬選択後: visible detail 1 / aria-pressed 1 / scrollWidth 375
1440px相当: visible mobile boards 0 / desktop formation 1 / desktop reason visible
```

### 未完了・次の具体的作業

- 次のスマホ優先改善は、トップのレース一覧を競馬場タブとコンパクトな1R〜12R行へ再構成する。
- 実装時は`apps/web/src/app/page.tsx`と一覧コンポーネントを確認し、PCの開催場横並びを維持する。
- ロケテスト公開へ反映する際は実行用クローンでpull後、Quick Tunnelを再起動する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 馬チップは48px基準。長い馬名は省略し、選択後の詳細で全文を表示する。
- 初期選択馬は設けない。自動的に特定馬を強調する要件は未確定。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/FormationView.tsx`
2. `apps/web/src/components/FormationView.test.tsx`
3. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 14:14 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `0dcc3e4`
- 目的: 確定後分析のスマホ画面を短くし、結果と振り返りへすぐ到達できるようにする。

### 完了内容

- `MobilePaceAnalysisDashboard`を追加し、768px未満を
  「サマリー・振り返り・全馬」の3タブへ分割した。
- モバイルHeroを日付、コース、レース名、実際の流れ、天候、馬場、分析頭数へ圧縮した。
- 初期サマリーは予想との答え合わせ、上位3頭、一言解説だけを表示する。
- 振り返りタブには実際の流れ、上位3頭の傾向、分析対象、初心者向け解説全文、
  算出根拠をまとめた。
- 全馬タブではPC用テーブルを使わず、着順、馬番、馬名、脚質、ペース傾向、
  上がり3Fを二段のコンパクト行で表示する。
- PCI・RPCIの内部実数値は画面へ追加せず、既存の記号と言語ラベルだけを使用した。
- 390px相当の小倉11Rで初期ページ高943px、上位3行、全馬18行、
  3タブ切替、ページ横はみ出しなしを確認した。
- 1440px相当ではモバイルタブと行が非表示になり、従来のPC用テーブルだけが表示された。

### 変更ファイル

1. `apps/web/src/components/MobilePaceAnalysisDashboard.tsx`
2. `apps/web/src/components/MobilePaceAnalysisDashboard.test.tsx`
3. `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`
4. `tasks/current.md`
5. `docs/DECISIONS.md`
6. `docs/HANDOFF.md`

### テスト結果

```text
Web: 103 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当サマリー: page height 943 / result rows 3 / scrollWidth 375
390px相当全馬: result rows 18 / scrollWidth 375 / 横スクロール表なし
390px相当振り返り: 解説全文・算出根拠あり / scrollWidth 375
1440px相当: visible mobile tabs 0 / mobile result rows 0 / desktop table 1
```

### 未完了・次の具体的作業

- トップのレース一覧はスマホでも開催場を縦に連続表示するため、開催日によってスクロールが長い。
- `apps/web/src/app/page.tsx`と一覧コンポーネントを確認し、768px未満だけ競馬場タブと
  コンパクトな1R〜12R行へ分離する。PCの開催場横並びは維持する。
- ロケテスト公開へ反映する際は実行用クローンでpull後、Quick Tunnelを再起動する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- 初期サマリーは上位3頭。取消・中止等で着順1〜3が欠ける場合は存在する着順だけを表示する。
- 全馬行は64px基準だが、長い馬名や端末文字サイズ設定では自動的に高くなる。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobilePaceAnalysisDashboard.tsx`
2. `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`
3. `apps/web/src/app/page.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 14:00 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `18604c4`
- 目的: スマホのレース詳細から、同一開催の前後レースへ素早く移動できるようにする。

### 完了内容

- `buildRaceNavigation()`を追加し、同日・同競馬場の実在レースだけを番号順に整列する。
- 出走前・確定後の両ページで日付指定のレース一覧APIを取得し、共通の
  `MobileRaceNavigation`へ渡す構成にした。
- 前R・次Rは44pxのアイコンボタン、1R〜12Rは横スクロール可能な番号列とし、
  現在Rを中央付近へ自動スクロールする。
- 遷移先は`raceHref()`に統一し、`entries`は予想、`result`は確定後分析へ移動する。
- レースキーの連番を推測しないため、欠番・中止・障害レースの状態差があっても
  APIに存在しない画面へのリンクを作らない。
- 一覧APIだけが失敗した場合はナビを省略し、取得済みの予想・分析画面は表示を継続する。
- 390px相当の新潟11Rで現在R中央表示、前R移動、内部スクロール、ページ横はみ出しなしを確認した。
- 確定後の小倉11Rでも、1R〜12Rの各状態に応じた正規リンクを確認した。

### 変更ファイル

1. `apps/web/src/lib/races.ts`
2. `apps/web/src/lib/races.test.ts`
3. `apps/web/src/components/MobileRaceNavigation.tsx`
4. `apps/web/src/components/MobileRaceNavigation.test.tsx`
5. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
6. `apps/web/src/components/RaceForecastDashboard.tsx`
7. `apps/web/src/app/races/[raceKey]/forecast/page.tsx`
8. `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`
9. `tasks/current.md`
10. `docs/DECISIONS.md`
11. `docs/HANDOFF.md`

### テスト結果

```text
Web: 101 passed
Web typecheck: passed
Web production build: passed
Web lint: package.jsonにlintスクリプトがないため実行不可
390px相当: viewport 375 / page scrollWidth 375 / nav clientWidth 230 / nav scrollWidth 532
新潟11R→10R: 前Rリンクで遷移し、現在Rと前後リンクが更新されることを確認
小倉11R確定後: 1R〜12Rの正規キーとstatus別遷移先を確認
1440px相当: モバイルナビ非表示 / viewport 1425 / scrollWidth 1425
```

### 未完了・次の具体的作業

- `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`はスマホでもPCと同じ連続構成で、
  各馬テーブルが縦長になる。予想画面と同様に、要約・振り返り・各馬結果を目的別に分ける。
- 実装時は`RaceHero`、`ForecastAccuracyBadge`、`CommentCard`、`PaceAnalysisTable`の内容を失わず、
  768px未満だけを専用コンポーネントへ分離する。
- ロケテスト公開へ反映する際は実行用クローンでpull後、Quick Tunnelを再起動する。

### 仮実装・暫定値・未確定仕様

- モバイル境界は既存方針どおりTailwindの`md`（768px）。
- レース番号列は現在Rを中央付近へ寄せるが、先頭・末尾ではブラウザの最大スクロール位置に従う。
- 専用ナビAPIは追加せず既存の日付指定一覧APIを利用する。件数や応答速度が問題になった場合だけ見直す。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobileRaceNavigation.tsx`
2. `apps/web/src/lib/races.ts`
3. `apps/web/src/app/races/[raceKey]/pace-analysis/page.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 13:50 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `cefdba9`
- 目的: スマホの注目馬タブを短くし、必要な馬の評価理由だけ確認できるようにする。

### 完了内容

- `MobileExpandableHorseRow`を追加し、展開恩恵馬TOP5と評価を下げたい馬を同じ行UIへ統一した。
- 閉じた状態では馬名、馬番または登録順、脚質、適性評価、役割ラベルだけを表示する。
- 行をタップすると「今回の評価理由」を展開し、他の馬は閉じたまま維持する。
- ネイティブ`details`を使い、JavaScript状態を増やさずキーボード操作と意味構造を保った。
- 390x844実画面で8行、初期open 0件、注目馬パネル高660px、1頭展開後open 1件、
  ページ幅375pxのまま横はみ出しなしを確認した。

### 変更ファイル

1. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
2. `apps/web/src/components/MobileRaceForecastDashboard.test.tsx`
3. `tasks/current.md`
4. `docs/DECISIONS.md`
5. `docs/HANDOFF.md`

### テスト結果

```text
Web: 97 passed
Web typecheck: passed
Web production build: passed
390x844注目馬: 8行 / 初期open 0 / panel height 660 / scrollWidth 375
1頭展開: open 1 / 理由表示あり / scrollWidth 375
```

### 未完了・次の具体的作業

- 次のスマホ優先改善は、同一開催の前後レースへ移動するナビゲーション。
- レースキーを文字列から推測せず、トップのレースボードデータまたは軽量APIから
  同一開催・同日・同競馬場の正規キーを取得する設計が必要。
- ロケテスト公開へ反映する際は実行用クローンでpull後、Quick Tunnelを再起動する。

### 仮実装・暫定値・未確定仕様

- 複数行を同時に開ける。1行だけに制限する必要性はロケテスト結果を見て判断する。
- コンパクト行の基準高は64px。端末の文字サイズ設定によっては自動的に高くなる。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
2. `apps/web/src/components/MobileRaceForecastDashboard.test.tsx`
3. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 13:40 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `87af564`
- 目的: レース詳細のスマホ版を短くし、最初の画面で展開と注目馬を判断できるようにする。

### 完了内容

- `MobileRaceForecastDashboard`を追加し、768px未満を
  「サマリー・隊列・注目馬・詳細」の4タブへ分割した。
- モバイルHeroを日付、コース、レース、想定展開、信頼度へ圧縮した。
- 初期サマリーを展開恩恵馬TOP3、初心者向け一文、注意馬1頭へ限定した。
- 全TOP5、注意馬一覧、判断サマリー、脚質別分析、コメント、判断根拠データは
  対応するタブ内に保持した。
- 枠順未確定時は`horseNumberLabel`を使い、暫定番号を公式馬番として表示しない。
- `FormationView`はモバイルのみ4ゾーン横スワイプ、デスクトップは従来の4列表示とした。
- 390x844実画面でサマリー、隊列、詳細タブを操作し、ページ横はみ出しなしを確認した。
  初期ページ高は936px、初期恩恵馬は3頭。隊列領域だけが横スクロール可能。
- 1440x900ではモバイル側が非表示となり、既存PCダッシュボードだけが表示されることを確認した。

### 変更ファイル

1. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
2. `apps/web/src/components/MobileRaceForecastDashboard.test.tsx`
3. `apps/web/src/components/RaceForecastDashboard.tsx`
4. `apps/web/src/components/FormationView.tsx`
5. `tasks/current.md`
6. `docs/DECISIONS.md`
7. `docs/HANDOFF.md`

### テスト結果

```text
Web: 96 passed
Web typecheck: passed
Web production build: passed
390x844: scrollWidth 375 / clientWidth 375 / initial height 936 / TOP3 3件
390x844隊列: ページ幅375のまま、隊列領域のみ横スクロール
1440x900: visible main 1件 / mobile tablist非表示 / 横はみ出しなし
```

### 未完了・次の具体的作業

- 実スマホのロケテストで、サマリーから各タブへの移動回数と見落としを確認する。
- 次段階では`MobileRaceForecastDashboard.tsx`の注目馬タブを、全カードではなく
  タップした馬だけ理由を展開するコンパクト行へ統一する。
- レース番号の前後移動・1R〜12R横ナビは、同一開催の隣接レース契約がAPIにないため未実装。
  実装時は一覧データまたは専用軽量APIから正規レースキーを取得し、キー推測で遷移しない。
- Quick Tunnelの公開プロセスは実行用クローン側で管理し、今回の検証用3200番サーバーは停止済み。

### 仮実装・暫定値・未確定仕様

- モバイル境界はTailwind既定の`md`（768px）。実端末フィードバックで見直す。
- 初期表示はTOP3、注意馬1頭。表示件数はロケテスト結果が出るまで暫定。
- タブ選択はページ再訪時にサマリーへ戻る。URL・localStorageへの保持は未実装。

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/MobileRaceForecastDashboard.tsx`
2. `apps/web/src/components/RaceForecastDashboard.tsx`
3. `apps/web/src/components/FormationView.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 11:53 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `e643ede`
- 運用検証記録コミット: `b76737c`
- 競合修正コミット: `395645d`
- 目的: Windows実行機でQuick Tunnelの実公開を検証し、代表3レースを確認する。

### 完了内容

- Cloudflare公式Windows版`cloudflared 2026.7.3`を
  `C:\Users\yuuta\AppData\Local\cloudflared\cloudflared.exe`へ導入した。
  Authenticode署名は`Valid`を確認した。
- Git管理外の`apps/web/.env.location-test.local`を作成し、共有ユーザー名と
  32文字の暗号学的ランダムパスワードを設定した。FastAPIは公開Bearer認証未設定のため
  `API_ACCESS_TOKEN`は空のまま。
- Quick Tunnel実URLで未認証401、共有認証200、Next.jsからFastAPIへの疎通を確認した。
- 実公開URLの認証済みページで次の3レースがHTTP 200となり、期待マーカーを確認した。
  - `2026072504020111`: 新潟11R、芝1000m、18頭
  - `2026072504020110`: 新潟10R、ダート1800m、15頭
  - `2026072504020107`: 新潟7R、新潟日報賞、芝1400m、18頭、枠順確定後
- 同じNext.js本番プロセスをローカルブラウザで開き、トップ、3代表レース、
  隊列予想を確認した。組み込みブラウザはTryCloudflareドメインを
  `ERR_BLOCKED_BY_CLIENT`で遮断したため、公開経路はHTTP検証、表示はlocalhostで分離確認した。
- 検証中に通常の`next dev`とロケテスト用`next build/start`が同じ`.next`を共有し、
  `lucide-react`のvendor chunkが欠損する競合を発見した。
  `NEXT_DIST_DIR=.next-location-test`をロケテスト時だけ設定して分離した。
- 競合修正後、開発サーバーを3000番で起動したまま、分離ビルド、3100番の本番起動、
  Quick Tunnel実URLの代表3レースを再確認した。
- 一時公開は停止済み。3100番の待受とロケテスト用cloudflaredプロセスがないことを確認した。
- 最初の検証に使った共有パスワードは破棄し、未使用の新しい32文字値へ交換した。

### 変更ファイル

1. `apps/web/next.config.mjs`
2. `apps/web/tsconfig.json`
3. `apps/web/.gitignore`
4. `apps/web/scripts/run_location_test_tunnel.ps1`
5. `README.md`
6. `docs/LOCATION_TEST.md`
7. `docs/DECISIONS.md`
8. `tasks/current.md`

### テスト結果

```text
cloudflared Authenticode: Valid
cloudflared version: 2026.7.3
Quick Tunnel自動検証: 未認証401 / 共有認証200 / API疎通 passed
実公開URLの代表3ページ: HTTP 200、期待マーカー 5 / 5 / 7 passed
Web: 95 passed
Web typecheck: passed
通常.next production build: passed
.next-location-test production build: passed
分離後next start 127.0.0.1:3110: HTTP 200、レースボード表示 passed
PowerShell 5.1 AST parse: passed
git diff --check: passed
```

### 未完了・次の具体的作業

- 招待開始時だけ`run_location_test_tunnel.ps1 -SkipBuild`を起動し、表示された新しいURLを共有する。
  今回の検証URLは停止済みで再利用できない。
- 参加者へはTryCloudflare URL、`BETA_ACCESS_USER`、`BETA_ACCESS_PASSWORD`だけを個別共有する。
  パスワードは`apps/web/.env.location-test.local`で確認し、チャットやGitへ記録しない。
- 開催2週後、`docs/LOCATION_TEST.md`の5項目、誤データ件数、API 500件数を集計する。
- 事前予想照合30件、ダート確定100件かつ実績ハイ20件は条件到達待ち。
- 修正前ログに残った可能性があるSlack Webhook再発行は、ユーザーのSlack操作待ち。

### 仮実装・暫定値・未確定仕様

- Quick Tunnelは3〜5人・開催2週分のテスト専用。URL固定、SLA、常時稼働は保証しない。
- 正式公開時のWeb/API/PostgreSQL基盤と個別ユーザー認証は未確定。
- ロケテスト専用ビルド名`.next-location-test`は運用競合回避の内部名で、公開契約ではない。

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `apps/web/scripts/run_location_test_tunnel.ps1`
3. `apps/web/next.config.mjs`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
powershell.exe -NoProfile -ExecutionPolicy Bypass -File apps\web\scripts\run_location_test_tunnel.ps1 -CloudflaredPath "C:\Users\yuuta\AppData\Local\cloudflared\cloudflared.exe" -SkipBuild
```

## 2026-07-25 11:24 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `181746b`
- 実装コミット: `9843b42`
- 目的: 初回少人数ロケテストの公開方式を決定し、安全に起動・停止できる状態を作る。

### 完了内容

- 現行PostgreSQLが約121MBであることを確認し、無料公開基盤の現行制約と比較した。
- 初回3〜5人・開催2週分は、Windows実行機のFastAPI/PostgreSQLをlocalhostに残し、
  Basic認証付きNext.jsだけをCloudflare Quick Tunnelで一時公開する方針に決定した。
- `apps/web/scripts/run_location_test_tunnel.ps1`
  - API/DB readiness、ループバックAPI、秘密値の分離、ポート、依存コマンド、
    Next.js本番ビルドを公開前に検査する。
  - Next.jsを`127.0.0.1:3100`で起動し、Quick Tunnel URLの未認証401、
    認証済み200、画面上のAPI疎通を確認してからURLを表示する。
  - 資格情報をログへ出さず、終了時にWebとトンネルの子プロセスを停止する。
- `apps/web/.env.location-test.example`を追加し、実値を入れる
  `.env.location-test.local`はGit管理対象外のままにした。
- `docs/LOCATION_TEST.md`へインストール、事前点検、公開、停止手順を追加した。
- Quick Tunnelはテスト専用であり、正式公開時はマネージド構成へ移行する判断を
  `docs/DECISIONS.md`と`docs/design/08-deployment.md`へ記録した。

### 未完了・作業が止まっている箇所

- Windows実行機に`cloudflared`が未導入のため、実TryCloudflare URLの発行は未実施。
- `.env.location-test.local`の実資格情報は未設定。秘密値のためリポジトリへ記録しない。
- 実URLでの代表3レース（芝短距離、ダート中距離、枠順確定後の多頭数）の目視確認は未実施。
- 事前予想照合30件、ダート確定100件かつ実績ハイ20件は条件到達待ち。
- Slack Webhook再発行はユーザーのSlack操作が必要。

### 仮実装・暫定値・未確定仕様

- Quick Tunnelは初回3〜5人・開催2週分だけの暫定公開方式。URL固定、SLA、常時稼働は保証しない。
- Next.jsローカル公開ポートは既定`3100`。使用中なら`-Port`で変更できる。
- 正式公開時のWeb/API/PostgreSQLサービス、費用、個別ユーザー認証は未確定。

### 既知の問題

- `cloudflared`がない状態では事前点検が明示的に失敗する。リポジトリは外部実行ファイルを
  自動インストールしない。
- Windows PowerShell 5.1はBOMなしUTF-8の日本語スクリプトを誤読するため、
  `run_location_test_tunnel.ps1`はUTF-8 BOM付きで管理する。

### テスト結果

```text
PowerShell 5.1 AST parse: passed
Quick Tunnel preflight（公開なし、cloudflared代替パス）: passed
Web: 95 passed
Web production build: passed（Middleware 34.9 kB）
Web typecheck（build後に単独再実行）: passed
git diff --check: passed
秘密設定: .env.location-test.local ignored / example tracked
```

型チェックと本番ビルドを最初に並列実行した際、ビルドが`.next/types`を再生成する競合で
型チェックだけ失敗した。ビルド完了後に同じ型チェックを単独再実行して成功しており、
コードの型エラーではない。

### Claude Codeが次に実施する具体的な手順

1. Cloudflare公式配布ページからWindows版`cloudflared`を導入する。
2. `apps/web/.env.location-test.example`を`.env.location-test.local`へコピーし、
   `BETA_ACCESS_USER`と16文字以上の`BETA_ACCESS_PASSWORD`を設定する。
3. `run_location_test_tunnel.ps1 -PreflightOnly`を実行し、全`PASS`を確認する。
4. 同スクリプトを通常実行し、発行URLで未認証401、共有認証後のトップ画面、
   代表3レースのレース名・距離・頭数・出走馬を確認する。
5. 問題がなければ3〜5人へURLとWeb共有資格情報だけを個別共有し、開催2週分の感想を集める。

### 対象ファイル

1. `apps/web/scripts/run_location_test_tunnel.ps1`
2. `apps/web/.env.location-test.example`
3. `docs/LOCATION_TEST.md`
4. `docs/design/08-deployment.md`
5. `docs/DECISIONS.md`
6. `tasks/current.md`

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `apps/web/scripts/run_location_test_tunnel.ps1`
3. `tasks/current.md`
4. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
copy apps\web\.env.location-test.example apps\web\.env.location-test.local
notepad apps\web\.env.location-test.local
powershell.exe -NoProfile -ExecutionPolicy Bypass -File apps\web\scripts\run_location_test_tunnel.ps1 -PreflightOnly
```

## 2026-07-25 11:04 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `5c86eda`
- 実装コミット: `23b62ea`
- 目的: 実行環境制約で残っていた取り込み警告UIのブラウザ検証を完了する。

### 完了内容

- 実APIを中継し、`ingest-status`だけ警告状態へ置き換える一時環境で
  `IngestStatusBanner`の閉じた初期表示と展開後を確認した。
- 1440x900と390x844でページ全体の横スクロールがないことを確認した。
- 展開後に失敗詳細、成績未取込対象、復旧コマンドが表示されることを確認した。
- モバイルで英字エラー文が1文字だけ残る折り返しを`break-all`から`break-words`へ修正した。
- ブラウザコンソールエラー0件を確認し、テスト用Web/API中継を停止した。
- 実DB、既存のlocalhost:3000、FastAPIのlocalhost:8000には変更を加えていない。

### テスト結果

```text
Web: 95 passed
Web typecheck: passed
Web production build: passed（Middleware 34.9 kB）
ブラウザ 1440x900: 初期表示・展開後とも横はみ出しなし
ブラウザ 390x844: 初期表示・展開後とも横はみ出しなし
ブラウザコンソール: error 0件
```

テスト追加直後は、エラー詳細を持たないfixtureへ折り返しクラスを期待したため1件失敗した。
`recent_failures`を含むfixtureへ修正後、Web全95件が成功している。

### 未完了・次の具体的作業

- 公開基盤と実URLを決め、`docs/LOCATION_TEST.md`の認証変数を設定する。
- 公開環境で`npm.cmd run location-test:preflight`を実行する。
- CLI合格後、芝短距離、ダート中距離、枠順確定後の多頭数レースを各1件目視確認する。
- 事前予想照合30件、ダート確定100件かつ実績ハイ20件は条件到達待ち。
- Slack Webhook再発行はユーザーのSlack操作が必要。

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `tasks/current.md`
3. `apps/web/src/components/IngestStatusBanner.tsx`
4. `apps/web/src/components/IngestStatusBanner.test.tsx`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
npm.cmd test --workspace=@pci/web
npm.cmd run typecheck --workspace=@pci/web
npm.cmd run build --workspace=@pci/web
```

## 2026-07-25 10:51 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `cbce875`
- 実装コミット: `26c151d`
- 目的: 公開基盤決定後に実行するロケテスト開始前HTTP点検を自動化する。

### 完了内容

- `scripts/location-test-preflight.mjs`
  - 秘密値を環境変数から読み、Web未認証401、API readiness、API未認証401、
    認証済みレース一覧、認証済みWeb表示を終了コードで判定する。
  - 公開HTTP、短い秘密値、秘密値の使い回し、Basic/Bearer要求ヘッダー欠落、
    トップ画面上のAPIエラー表示を不合格にする。
  - URL、判定名、HTTP状態以外に共有パスワードやAPIトークンを出力しない。
- `scripts/location-test-preflight.test.mjs`
  - Node標準HTTPサーバーで正常系、readiness異常、Web APIエラー表示を再現する。
  - 設定検証を含む8 testsを追加した。
- ルート`package.json`へ`location-test:preflight`と`test:location-test-preflight`を追加した。
- `docs/LOCATION_TEST.md`へ実行環境変数、合格条件、CLIでは代替できない代表3レースの
  目視確認を記録した。

### テスト結果

```text
公開前点検CLI: 8 passed
Web: 95 passed
Web typecheck: passed
api-client typecheck: passed
API公開認証契約: 5 passed
Web production build: passed（Middleware 34.9 kB）
```

### 未完了・作業が止まっている箇所

- 公開基盤と実URLは未決定のため、公開環境に対するCLI実行は未実施。
- 公開後は`docs/LOCATION_TEST.md`に従い、認証変数を設定して
  `npm.cmd run location-test:preflight`を実行する。
- CLI合格後、芝短距離、ダート中距離、枠順確定後の多頭数レースを各1件目視確認する。
- 事前予想照合30件、ダート確定100件かつ実績ハイ20件は条件到達待ち。
- Slack Webhook再発行はユーザーのSlack操作が必要。

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `scripts/location-test-preflight.mjs`
3. `scripts/location-test-preflight.test.mjs`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
npm.cmd run test:location-test-preflight
```

## 2026-07-25 10:35 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `ed5d0ee`
- 目的: 条件待ちタスクを飛ばし、次に実行可能な少人数ロケテスト用アクセス制限を実装する。

### 完了内容

- `apps/web/src/middleware.ts`
  - `BETA_ACCESS_USER`・`BETA_ACCESS_PASSWORD`設定時に全画面を共有Basic認証で保護する。
  - 片方だけ設定された場合は503、両方未設定ならローカル開発を維持する。
- `apps/web/src/lib/betaAccess.ts`
  - UTF-8資格情報、パスワード中のコロン、不正Base64を扱い、比較値をログへ出さない。
- `apps/api/src/pci/presentation/app.py`
  - `PUBLIC_API_TOKEN`設定時に`/api/v1/*`へBearer認証を要求する。
  - `/health`・`/ready`と`/internal/ingest/*`は対象外とし、既存認証を分離する。
- `packages/api-client/src/index.ts`へ固定ヘッダー指定を追加し、Next.jsの
  `API_ACCESS_TOKEN`をFastAPIへ送る。
- `.env.example`、README、ARCHITECTURE、SPEC、DECISIONS、LOCATION_TEST、currentを更新した。

### HTTP実地確認

```text
Web（BETA_ACCESS_*設定、localhost:3001）:
  未認証 401 / 誤資格情報 401 / 正しい資格情報 200

API（PUBLIC_API_TOKEN設定、127.0.0.1:8001）:
  /ready 200 / 未認証 401 / 誤トークン 401 / 正しいトークン 200

Web→API（API_ACCESS_TOKEN設定、localhost:3002）:
  レース日、検証成績、取り込み状態、レースボードのAPI呼び出しがすべて200
```

### テスト結果

```text
API非統合: 596 passed, 30 deselected
API Ruff（src/tests）: passed
API mypy strict: 65 files passed
公開API認証契約: 5 passed
Web: 95 passed
Web typecheck: passed
api-client typecheck: passed
Web production build: passed（Middleware 34.9 kB）
```

### 未完了・既知事項

- 公開基盤は未決定。Vercel等のWeb環境とFastAPI環境へ4つの認証変数を設定し、
  `docs/LOCATION_TEST.md`の開始前点検を行う必要がある。
- 共有Basic認証は個別アカウント管理ではない。参加者変更・テスト終了時は共有パスワードを更新する。
- 予想照合30件、ダート100件かつハイ20件は引き続き条件到達待ち。
- Slack Webhook再発行はユーザーのSlack操作が必要で未完了。

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `apps/web/src/middleware.ts`
3. `apps/api/src/pci/presentation/app.py`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
cd apps\web
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

## 2026-07-25 02:34 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `3dd8335`
- 実装コミット: `d2e9258`, `15f9d88`
- 目的: 推奨順に品質・UI・資料を改善し、少人数ロケテストへ進むための条件を整える。

### 完了内容

- 実DBでダートRPCI v4監視を実行した。2026-07-25以降の確定ダートは0件で`no_data`。
- 90日予想検証は対象787レース、保存済み事前予想0件、カバー率0%。係数は変更せず蓄積を続ける。
- ingestion-workerの既存Ruff/mypy違反を解消した。
  - `client/windows_client.py`
  - `client/mykeibadb_client.py`
  - `locate_corners.py`
  - `tests/test_locate_corners.py`
- API全体Ruffを妨げていた`apps/api/scripts/seed_dev.py`の未使用アンパックと長い行を修正した。
- `forecastDecisionChecklist()`へ`integratedRanking`を渡し、冒頭の候補を展開適性単独1位から
  統合順位上位3頭へ変更した。注意馬と「予想精度は検証データを蓄積中」も追加した。
- `IntegratedRankingView`は上位5頭を初期表示し、6位以下を`details`へ格納した。
- 1440×900と390×844で実画面を確認し、横スクロールなし、文字の重なりなしを確認した。
- README、ARCHITECTURE、SPEC、DECISIONS、currentを現状へ更新した。
- `docs/LOCATION_TEST.md`へ開始条件、点検手順、感想項目、停止条件を追加した。

### 仮実装・暫定値・未確定仕様

- 想定RPCI/PAI等の係数と閾値は引き続き仮仕様。照合0件のため今回変更していない。
- ロケテストのアクセス制限方式と公開基盤は未確定。認証なしの外部公開は禁止。
- ロケテストは照合30件未満でもUI確認に限定して実施可能だが、予想精度の評価には使わない。

### 未完了・既知事項

- 事前予想照合が30件に到達した時点で、全体・芝・ダートの初回不一致レビューを行う。
- ダート確定100件かつ実績ハイ20件で`--monitor-dirt-v4 --fail-on-monitoring-review`を再実行する。
- 修正前ログにWebhook URLが残った可能性があるため、Slack側でWebhookを再発行する。
- 公開前にWeb/API両方のアクセス制限方式を決定・実装し、開始前点検を実施する。

### テスト結果

```text
ingestion-worker:
  python -m ruff check src tests: passed
  python -m mypy src --strict --python-version 3.12: 24 files passed
  python -m pytest -q: 239 passed, 1 sandbox cache warning

web:
  npm.cmd test --workspace=@pci/web: 83 passed
  npm.cmd run typecheck --workspace=@pci/web: passed
  npm.cmd run build --workspace=@pci/web: passed

api:
  python -m pytest -m "not integration" -q: 591 passed, 30 deselected
  python -m ruff check src tests scripts: passed
  python -m mypy src --strict --python-version 3.12: 65 files passed
  import-linter: 2 contracts kept, 0 broken

実画面:
  1440x900: horizontal overflow なし
  390x844: horizontal overflow なし
```

### Claude Codeが最初に確認するファイル

1. `docs/LOCATION_TEST.md`
2. `apps/web/src/lib/pace.ts`の`forecastDecisionChecklist`
3. `apps/web/src/components/IntegratedRankingView.tsx`
4. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```cmd
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
cd apps\web
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
```

## 2026-07-25 02:40 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `c8468f8`
- 実装コミット: `d383b9b`
- 目的: WindowsのWebhook通知を重複なく安全に送り、実環境で到達確認する。

### 完了内容

- `apps/ingestion-worker/src/ingestion/batch.py`
  - `INGEST_NOTIFICATION_OWNER=wrapper`時はPython側通知をラッパーへ委譲する。
  - 通知中のhttpx INFOログを抑え、例外中のWebhook URLを`<redacted>`へ置換する。
  - `raise_for_status()`でHTTPエラーを通知成功として扱わない。
- `apps/ingestion-worker/scripts/run_batch.ps1`
  - 全リトライ失敗後に1回だけ通知する。
  - TLS 1.2と通常の証明書検証を維持し、例外中のURLを秘匿する。
  - 取り込みを伴わない`-TestNotification`を追加した。
- `apps/ingestion-worker/tests/test_batch_notifications.py`
  - ラッパー配下の重複通知抑止、URL秘匿、httpxログレベル復元を固定した。
- Windows実行機からSlackへのテスト通知に成功し、専用ログにURLがないことを確認した。

### テスト結果

```text
pytest tests/test_batch_notifications.py -q: 2 passed
対象Ruff: passed
PowerShell AST parse: passed
run_batch.ps1 -TestNotification: exit 0、送信成功
webhook-testログのURL検索: 0件
```

全worker Ruffは今回無関係の`windows_client.py`・`locate_corners.py`等14件で失敗した。
全worker mypy strictも既存の型スタブ不足・`mykeibadb_client.py`等20件で失敗した。
今回変更ファイルのRuffと通知テストは成功している。

### 未完了・既知事項

- 修正前の古いローカルログにWebhook URLが記録されているため、Slack側でWebhookを再発行し、
  `apps/ingestion-worker/.env`のURLを更新する。旧ログやURLをリポジトリへコミットしない。
- ダートRPCI v4初回期間外レビューは標本条件到達待ち。

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/scripts/run_batch.ps1`
2. `apps/ingestion-worker/src/ingestion/batch.py`
3. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
.\scripts\run_batch.ps1 -TestNotification
```

## 2026-07-25 02:30 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `0e88e5c`
- 実装コミット: `20daa55`
- 目的: JST修正の未実施検証を完了し、Windows取り込みログの日本語文字化けを解消する。

### 完了内容

- JST固定オフセットの回帰テスト4件、対象Ruff、API全体のmypy strictを完了した。
- 実環境で2026-07-25〜08-08の予想事前生成を実行し、対象72・生成72・スキップ0、API 200を確認した。
- `apps/ingestion-worker/scripts/run_batch.ps1`
  - コンソール入出力、PowerShell外部出力、Python標準入出力をUTF-8へ統一した。
  - `Tee-Object`を廃止し、外部出力を画面表示しながらUTF-8でログへ追記するようにした。
- `apps/ingestion-worker/scripts/sync_mykeibadb.bat`
  - コードページ65001、`PYTHONUTF8=1`、`PYTHONIOENCODING=utf-8`を設定した。
- Windows PowerShell 5.1のラッパー経由で予想72件を再生成し、コンソールと
  `logs/20260725-forecasts.log`の日本語が正しく読めることを確認した。

### テスト結果

```text
pytest tests/unit/application/test_forecast_precompute_use_cases.py -q: 4 passed
ruff check forecast_precompute_use_cases.py + test: passed
mypy src --strict --python-version 3.12: 65 files passed
PowerShell AST parse: passed
run_batch.ps1 -Step forecasts: 対象72 / 生成72 / スキップ0、exit 0
保存ログUTF-8読取: passed
```

### 未完了・既知事項

- ダートRPCI v4初回期間外レビューは、2026-07-25以降の確定ダート100件かつハイ20件到達待ち。
- 失敗通知時のSSL証明書エラーは別の既知運用課題。
- 既存の古い文字化け済みログは変換せず、修正後に生成・追記するログからUTF-8を保証する。

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/scripts/run_batch.ps1`
2. `apps/ingestion-worker/scripts/sync_mykeibadb.bat`
3. `tasks/current.md`

### Claude Codeが最初に実行するコマンド

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
powershell -ExecutionPolicy Bypass -File scripts\run_batch.ps1 `
  -Step forecasts -Mode mykeibadb -Date 20260725 -DateTo 20260808 -MaxRetries 1
```

## 2026-07-25 02:20 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `15bd5fb`
- 実装コミット: `896e21c`
- 目的: API・PostgreSQL停止中の全同期による連続500と部分実行を、処理開始前に防止する。

### 完了内容

- `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
  - `API_BASE_URL/ready`を同期開始前に確認する`Test-IngestApiReadiness`を追加した。
  - `status=ready`かつ`database=ok`の場合だけmykeibadb.exeと取り込み処理を開始する。
  - 利用不能時はmykeibadb.exe起動前に終了コード1で停止し、Docker Desktop、DBコンテナ、
    Alembic、FastAPIの復旧手順をログへ表示する。
  - データ更新を行わない`-PreflightOnly`を追加した。
- `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`、`README.md`、`docs/SPEC.md`、
  `docs/DECISIONS.md`、`tasks/current.md`、`tasks/backlog.md`へ運用・設計判断を反映した。

### テスト結果

```text
PowerShell AST parse: 成功
-PreflightOnly（API・DB正常）: exit 0、mykeibadb.exe未起動
-PreflightOnly（API_BASE_URL=http://127.0.0.1:65534）:
  exit 1、復旧手順を表示、mykeibadb.exe未起動
```

### 未完了・既知事項

- 前タスクのJST固定オフセット回帰テスト、Ruff、修正後の実環境予想生成は未実行のまま。
- 同期ログの文字化けと失敗通知時のSSL証明書エラーは別の既知運用課題。
- 事前確認はインフラを自動起動せず、復旧操作は運用者が行う。

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
2. `tasks/current.md`
3. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
powershell -ExecutionPolicy Bypass -File .\scripts\run_mykeibadb_full_sync.ps1 -PreflightOnly
```

## 2026-07-25 01:45 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `d39cb7e`
- 実装コミット: `2044e7b`
- 目的: mykeibadb同期とWebで発生したAPI 500の原因を切り分け、最新データを再同期する。

### 原因と復旧

1. Docker Desktopが停止し、PostgreSQL `localhost:5432`が接続拒否していた。
   `/health`はプロセス死活だけのため200、`/ready`はDB接続不能だった。
2. Docker Desktopと`db`コンテナを起動し、Alembic headを確認した。
3. 同期再実行で出馬表144レース、馬場情報72件、確定成績69レース、特別登録は成功した。
   問題として報告された`2026071802011101`も出馬表8頭・結果ともAPI 200で登録できた。
4. 最後の予想事前生成だけ、Windowsに`tzdata`がなく
   `ZoneInfoNotFoundError: No time zone found with key Asia/Tokyo`で失敗した。

### 変更内容

- `apps/api/src/pci/application/forecast_precompute_use_cases.py`
  - `ZoneInfo("Asia/Tokyo")`を、既存機能と同じUTC+9のJST固定オフセットへ変更した。
- `apps/api/tests/unit/application/test_forecast_precompute_use_cases.py`
  - JSTオフセットが9時間であることを固定する回帰テストを追加した。

### 未完了・既知事項

- Codexのコマンド実行承認利用上限により、追加した単体テスト・Ruffと、修正後の予想事前生成は未実行。
- 同期ログの文字化けと、失敗通知時のSSL証明書エラーは今回の500原因ではなく、別の既知運用課題。
- APIコードを反映した後はAPIプロセスの再起動が必要。

### Claude Codeが最初に実行するコマンド

```powershell
cd apps\api
$env:PYTHONPATH="src"
python -m pytest tests\unit\application\test_forecast_precompute_use_cases.py -q
python -m ruff check src\pci\application\forecast_precompute_use_cases.py `
  tests\unit\application\test_forecast_precompute_use_cases.py
python -m mypy src --strict --python-version 3.12

cd ..\ingestion-worker
python -m ingestion.batch --mode mykeibadb --date 20260715 --date-to 20260808 --step forecasts
```

予想生成後に`http://localhost:8000/ready`とWebトップを確認する。

## 2026-07-25 01:29 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `2619925`
- 実装コミット: `418771a`
- 目的: 取り込み警告がレース一覧を初期画面下方へ押し下げる問題を解消し、復旧情報を失わずコンパクトにする。

### 完了した内容

- `apps/web/src/components/IngestStatusBanner.tsx`
  - 失敗、成績未取込、馬場情報未反映、重複、再同期、馬場補完の個別`details`を廃止した。
  - 警告の見出しと要点を常時表示し、全詳細を「詳細と復旧手順」1つへ集約して既定で閉じた。
  - 件数、代表対象、レースリンク、失敗内容、コピー可能な復旧コマンドはすべて維持した。
  - 開閉状態を示すChevronとキーボードフォーカス表示を追加した。
- `apps/web/src/components/IngestStatusBanner.test.tsx`
  - 警告時の開閉領域が1つで閉状態、正常時は存在しないことを静的描画で検証した。
- `apps/web/vitest.config.ts`
  - TSXテスト、React automatic JSX、`@`エイリアスを有効化した。

### 未完了・作業が止まっている箇所

- 実装上の未完了はない。
- Codex実行環境のブラウザ接続が`EPERM: operation not permitted, lstat 'C:\Users\yuuta\AppData'`
  で初期化できず、デスクトップ・モバイルの自動スクリーンショット検証のみ未実施。
- 仮実装・暫定値・API契約・DB変更はない。

### テスト結果

```text
npm.cmd test --workspace=@pci/web
7 files / 83 tests passed

npm.cmd exec tsc --workspace=@pci/web -- --noEmit
成功

npm.cmd run build --workspace=@pci/web
Next.js 15.5.19 production build 成功

git diff --check
エラーなし（WindowsのLF→CRLF予告のみ）
```

### Claude Codeが最初に確認するファイル

1. `apps/web/src/components/IngestStatusBanner.tsx`
2. `apps/web/src/components/IngestStatusBanner.test.tsx`
3. `apps/web/vitest.config.ts`
4. `docs/DECISIONS.md`末尾の取り込み警告ADR
5. `tasks/current.md`先頭

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
npm.cmd test --workspace=@pci/web
npm.cmd exec tsc --workspace=@pci/web -- --noEmit
npm.cmd run dev --workspace=@pci/web
```

ブラウザで警告のあるトップ画面をデスクトップとモバイル幅で開き、初期状態がコンパクトであること、
「詳細と復旧手順」の展開後に全カテゴリとコマンドが表示されることを確認する。

## 2026-07-24 16:50 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `a9f1712`
- 目的: migration 006未適用でも従来のreadinessが正常判定する欠落を解消する。

### 完了した内容

- `apps/api/src/pci/infrastructure/database/readiness.py`
  - ORM必須テーブル・列の存在に加え、長さ付き文字列列の実DB容量を検査する。
  - 実DB長がORMの必要長より短い場合は`schema_outdated`を返す。
  - 長さ無制限の`TEXT`は互換として扱う。
- migration 006未適用相当の`predicted_pace.model_version VARCHAR(20)`を検出できる。
- `/ready`、OpenAPI、Webの復旧表示は既存契約を維持し、追加の公開項目はない。

### 未完了・既知事項

- 文字列長以外の型精度、nullable、index、constraintの完全比較は対象外。
- migration 006は実行用DBへ適用済みであり、現在の`/ready`は正常になる想定。
- ダートRPCI v4の初回期間外レビューは引き続きデータ蓄積待ち。

### テスト結果

```text
pytest tests/unit/infrastructure/database/test_readiness.py tests/contract/test_health_api.py -q
9 passed
pytest tests/integration/test_database_readiness.py -q
3 passed
mypy src --strict --python-version 3.12
Success: 65 source files
ruff check src/pci/infrastructure/database/readiness.py
All checks passed
```

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/infrastructure/database/readiness.py`
2. `apps/api/tests/unit/infrastructure/database/test_readiness.py`
3. `apps/api/tests/integration/test_database_readiness.py`
4. `docs/DECISIONS.md`末尾のreadiness ADR

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
python -m alembic current
python -m pytest tests\unit\infrastructure\database\test_readiness.py `
  tests\contract\test_health_api.py -q
```

## 2026-07-24 16:10 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `1ffd457`
- 目的: ダートRPCI v4の期間外品質を定期判定し、再学習レビュー条件を機械化する。

### 完了した内容

- `apps/api/src/pci/application/rpci_monitoring.py`
  - `no_data`、`accumulating`、`healthy`、`retraining_review`、`model_mismatch`を判定する。
  - 100レース・ハイ20レース未満では結論を出さない。
  - MAE、展開一致率、ハイ再現率、絶対バイアスの4条件を判定する。
- `apps/api/scripts/backtest_forecast.py`
  - `--monitor-dirt-v4`、`--fail-on-monitoring-review`を追加した。
  - 監視時はダート、全件サンプリング、本番モデル、2026-07-25以降を安全な既定値とする。
  - 通常のバックテストJSONへ`rpci_monitoring`を追加する。
- `apps/api/alembic/versions/006_expand_mart_model_version.py`
  - v4モデル名24文字を保存できるよう、martの`model_version`を20文字から64文字へ拡張した。
- 実DB再現
  - 2026-06-01以降197件はMAE4.750、一致率72.6%、ハイ90.6%、絶対バイアス2.619で`healthy`。
  - 採用後の2026-07-25以降は現時点で0件のため`no_data`。

### 監視条件

| 条件 | 値 | 根拠 |
|---|---:|---|
| 判定開始 | 全体100件かつハイ20件 | 少数標本での再学習判断を避ける |
| MAE | 5.94以下 | 採用時4.750から25%まで |
| 展開一致率 | 60%以上 | 既存受入基準 |
| ハイ再現率 | 60%以上 | 重要区分の最低受入基準 |
| 絶対バイアス | 4.62以下 | 採用時2.619から約2.0まで |

### 未完了・次に実施する具体的な手順

1. API起動前に`cd apps/api && python -m alembic upgrade head`を実行し、migration 006を適用する。
2. 2026-07-25以降の確定ダートが100件かつハイ20件へ到達したら、次を実行する。
   `python -m scripts.backtest_forecast --monitor-dirt-v4 --limit 200 --output
   results/dirt-v4-monitor.json --fail-on-monitoring-review`
3. `retraining_review`なら、同一対象期間で現行v4と再学習候補を比較する。本番ファイルを直接上書きしない。
4. 初回結果を`tasks/current.md`と本ファイルへ追記する。

### 仮実装・暫定値・既知事項

- 100件、ハイ20件、25%のMAE余地、バイアス約2.0の余地は初回運用基準。初回レビュー後に再検証する。
- 条件未達は再学習候補の比較開始を意味し、自動採用・自動ロールバックはしない。
- 採用後の確定レースがまだないため、本番期間での判定結果は未取得。
- Codex領域ではpytestキャッシュ作成警告が出るが、テスト結果には影響しない。

### テスト結果

```text
pytest tests/unit/application/test_rpci_monitoring.py tests/unit/test_backtest_forecast_cli.py -q
11 passed
pytest -m "not integration" -q
588 passed, 29 deselected
pytest tests/integration/test_mart_repository.py -q
4 passed
mypy src --strict --python-version 3.12
Success: 65 source files
ruff check src tests scripts/backtest_forecast.py
All checks passed
```

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/rpci_monitoring.py`
2. `apps/api/scripts/backtest_forecast.py`
3. `apps/api/alembic/versions/006_expand_mart_model_version.py`
4. `docs/DECISIONS.md`末尾の監視ADR
5. `tasks/backlog.md`の「ダートRPCI v4の初回期間外レビュー」

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
python -m alembic upgrade head
python -m scripts.backtest_forecast --monitor-dirt-v4 --limit 200
```

## 2026-07-24 15:04 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `2b68d31`
- 実装コミット: `13bc114`、`bd4d6c6`
- 目的: S3/L3履歴を使うRPCI v4を実装し、学習期間外のレースで本番v1と比較して採否を決める。

### 完了した内容

- `apps/api/src/pci/domain/pace/rpci_forecast.py`
  - 1頭分の過去レース前後半3F差を表す`HistoricalLapSample`を追加した。
  - `RaceContext`へ`historical_lap_samples`を追加した。
- `apps/api/src/pci/application/forecast_use_cases.py`
  - 対象日より前の各馬最大10走から、両方の3F値がある過去走だけを集約する。
  - 学習SQLと同じく`後半3F－前半3F`の馬単位平均と標本数を構築する。
- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
  - v3の33特徴量へ、履歴保有馬数・標本数・平均差・最小差・幅・カバー率を追加した。
  - 39特徴量をv4として自動判別し、芝・ダートで異なるモデル世代を利用できる。
  - 既定ダートモデルを`rpci_lgbm_dirt_v4.txt`へ切り替えた。芝はv1を維持する。
- `apps/api/scripts/train_rpci_lgbm.py`
  - `--feature-set v4`とS3/L3履歴のLATERAL JOINを追加した。
  - `--before-date`を追加し、最終評価期間を学習から完全に除外できるようにした。
- `apps/api/models/rpci_lgbm_dirt_v4.txt`
  - 2026-06-01より前の直近2,000件を使用し、古いラップ欠損期間の希釈を抑えて学習した。
  - 既存`rpci_lgbm_dirt_v1.txt`はロールバック用として保持した。

### 独立評価結果

学習は`race_date < 2026-06-01`、最終評価は`2026-06-01`以降に完全分離した。

| 対象 | モデル | 件数 | MAE | 展開一致 | ハイ再現 | 平均再現 | スロー再現 | 最上位帯 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 芝 | v1 | 200 | 4.834 | 62.5% | 79.6% | 6.7% | 59.7% | 0.99x |
| 芝 | v4 | 200 | 2.914 | 56.0% | 57.4% | 33.3% | 64.5% | 1.23x |
| ダート | v1 | 197 | 12.810 | 11.2% | 0.0% | 56.4% | 0.0% | 1.01x |
| ダート | v4 | 197 | 4.750 | 72.6% | 90.6% | 79.5% | 30.8% | 1.19x |

- 芝v4はMAEとPAI順位指標が改善したが、展開一致率とハイ再現率が悪化したため不採用。
- ダートv4は主要指標がすべて改善したため採用。

### 未完了・作業が止まっている箇所

- ダートv4の評価期間は197件で、期間外の継続監視は未実施。
- ダートv4のRPCIバイアスは`+2.619`残る。
- 再学習に必要な新規レース件数、許容悪化幅、モデル降格基準は未確定。
- 芝v4候補は不採用とし、候補モデルファイルを削除した。

### 次に実施する具体的な手順

1. `apps/api/scripts/backtest_forecast.py`で新規確定ダートレースを期間指定し、
   `lgbm-dirt-v4-lap-history`の展開一致率・3区分再現率・バイアスを継続記録する。
2. 独立評価が最低300件へ増えた時点で、今回と同じv1/v4比較を再実行する。
3. `tasks/backlog.md`の「ダートRPCI v4の期間外監視と再学習条件の確定」で、
   許容悪化幅と再学習件数を実測から決める。根拠なしの固定閾値は設定しない。

### 仮実装・暫定値・未確定仕様・既知事項

- 最大10走、6集約特徴量、学習上限2,000件は候補比較で採用した暫定設計。
- 距離差・競馬場差による履歴絞り込みは根拠未確定のため実装していない。
- 区間ラップは距離帯で欠損率が偏るためv4へ含めていない。
- UI・公開Race DTOへS3/L3、PCI、RPCIの実数値は追加していない。
- `import-linter`はグローバルPythonに`lint_imports`がなく実行できなかった。
- Codex領域ではpytestキャッシュ作成警告が1件出る。

### テスト実行コマンドと結果

```powershell
cd apps\api
$env:PYTHONPATH='src'
python -m pytest -m "not integration" -q
# 577 passed, 28 deselected
python -m mypy src --strict --python-version 3.12
# Success: 64 source files
python -m ruff check src\pci\domain\pace\rpci_forecast.py `
  src\pci\application\forecast_use_cases.py `
  src\pci\infrastructure\pace\lgbm_forecaster.py `
  scripts\train_rpci_lgbm.py `
  tests\unit\infrastructure\pace\test_lgbm_forecaster.py `
  tests\unit\test_train_rpci_lgbm.py `
  tests\unit\application\test_forecast_use_cases.py
# All checks passed
python -m scripts.backtest_forecast --track-type ダート --limit 1
# model_version=lgbm-dirt-v4-lap-history、ロード・予測成功
```

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/DECISIONS.md`の「RPCI v4はダート専用モデルだけを採用する」ADR
3. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
4. `apps/api/scripts/train_rpci_lgbm.py`
5. `apps/api/src/pci/application/forecast_use_cases.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\infrastructure\pace\test_lgbm_forecaster.py `
  tests\unit\test_train_rpci_lgbm.py `
  tests\unit\application\test_forecast_use_cases.py -q
python -m scripts.backtest_forecast --track-type ダート --limit 1
```

## 2026-07-24 13:25 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `772dd9b`
- 実装コミット: `30a59e8`、`18df8a6`
- 目的: RPCI v4候補で利用するレース前半3F・後半3Fを内部永続化し、直近1年をバックフィルする。

### 完了した内容

- `apps/api/alembic/versions/005_add_race_lap_times.py`
  - `races.race_s3f`・`races.race_l3f`をnullable列として追加した。
- `apps/api/src/pci/domain/racing/race.py`、
  `apps/api/src/pci/infrastructure/database/models.py`、
  `apps/api/src/pci/infrastructure/repositories/race_repository.py`
  - 内部3F値をドメイン・DB・Repositoryで往復できるようにした。
- `apps/api/src/pci/application/race_use_cases.py`
  - 結果取り込みで入力された3F値を保存し、片側欠損や出走表・メタデータの再取り込みで
    既存値を消さないようにした。
  - 保存済み値と今回値を統合してからRPCIを再計算する。
- `apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`
  - wmykeibadbの`352`形式を35.2秒へ正規化してからJV固定長へ書く。
  - 秒形式も受け付け、25.0〜50.0秒外は異常値として除外する。
- 実行用`C:\Users\yuuta\PCI_app`を`18df8a6`へfast-forwardし、DBをAlembic `005`へ更新した。
- `2025-07-24→2026-07-23`を`--step results --chunk-days 365`で再同期した。
  3,329レース成功、0レース失敗。再同期対象3,329件すべてでS3/L3を保存した。
- DB期間全体は確定済みJRA平地3,332件中3,329件（99.9%）でS3/L3両方を保持する。
  ダートは1,638/1,638件、芝は1,691/1,694件。

### 未完了・作業が止まっている箇所

- RPCI v4の学習特徴量とオンライン予測特徴量は未実装。
- S3/L3未保存の芝3件は今回のmykeibadb再同期集合に存在しない既存レコード。
  レースキーは`2026042609011001`、`2026050308011101`、`2026051005011101`。
  削除や補完はデータ来歴を確認するまで行っていない。
- 区間ラップはDBへ永続化しておらず、v4初期候補でも必須にしない。

### 次に実施する具体的な手順

1. `apps/api/scripts/train_rpci_lgbm.py`のv3特徴量定義を維持したまま、
   対象レース日より前の`races.race_s3f`・`race_l3f`履歴集約をv4候補として追加する。
2. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`へ同じ時点条件の
   オンライン特徴量を追加し、特徴量数によるv1/v2/v3/v4判別テストを更新する。
3. `apps/api/scripts/backtest_forecast.py`で芝・ダート各200レースを本番v1と比較し、
   MAEだけでなく展開一致率・ハイ再現率・最上位帯リフトを評価する。
4. 未保存3レースは`reconcile_duplicate_races`・mykeibadb `race_shosai`を照合し、
   正規レースでないと確認できた場合だけ別タスクで整理する。

### 仮実装・暫定値・未確定仕様・既知事項

- S3/L3の25.0〜50.0秒は既存RA parserと揃えた物理妥当範囲であり、モデル採用閾値ではない。
- v4で使う履歴件数、集約統計、距離差許容、欠損時の特徴量は未確定。
- v4候補は独立比較前に本番モデルへ採用しない。
- ingestion-worker全体Ruffは既存14件、全体mypy strictは既存20件で失敗する。
  今回変更した2ファイルのRuffは成功している。
- Codex領域ではpytestキャッシュ作成警告が1件出る。
- 実行用リポジトリの既存未追跡
  `apps/ingestion-worker/.env]`と`apps/ingestion-worker/result_run.txt`には触れていない。

### テスト実行コマンドと結果

```powershell
cd apps\api
$env:PYTHONPATH='src'
python -m pytest -m "not integration" -q
# 570 passed, 28 deselected
python -m pytest tests\integration\test_race_repository.py `
  tests\integration\test_database_readiness.py -q
# 19 passed
python -m mypy src --strict
# Success: 64 source files

cd ..\ingestion-worker
$env:PYTHONPATH='src'
python -m pytest -q
# 237 passed
python -m ruff check src\ingestion\client\mykeibadb_client.py `
  tests\test_mykeibadb_client.py
# All checks passed
```

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/DECISIONS.md`の「S3/L3は内部分析値として永続化」ADR
3. `apps/api/src/pci/application/race_use_cases.py`
4. `apps/api/scripts/train_rpci_lgbm.py`
5. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\application\test_race_use_cases.py `
  tests\contract\test_ingest_api.py -q
python -m alembic heads
```

## 2026-07-24 10:19 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `7457330`
- 実装コミット: `e302fd0`
- 目的: RPCI v4候補へラップ履歴を追加する前に、mykeibadb実データの欠損率を距離帯別に診断する。

### 完了した内容

- `apps/ingestion-worker/src/ingestion/diagnose_lap_coverage.py`
  - `race_shosai`の確定レコードだけを読み、JRA平地以外を除外する。
  - 同一レースキーの複数行は、S3/L3と区間ラップの情報量が多い行だけを採用する。
  - 芝・ダートと4距離帯に分け、S3、L3、S3+L3、区間ラップ一部、区間ラップ完全の件数・割合を出力する。
  - `--min-races`と`--min-coverage`を可変の診断条件とし、`--output`では集計JSONだけを保存する。
  - 生ラップ値、レース識別情報、認証情報はJSONへ含めない。
- `apps/ingestion-worker/tests/test_diagnose_lap_coverage.py`
  - 芝ダート・距離帯集計、確定前・障害除外、重複排除、1/10秒変換、異常値除外、入力検証を確認した。

### 実mykeibadb診断結果

実行期間は`2025-07-24→2026-07-23`、判定条件は最低200レース・カバー率80%。

| 馬場 | 距離帯 | 件数 | S3+L3 | 区間ラップ完全 | 診断 |
|---|---:|---:|---:|---:|---|
| ダート | 1399m以下 | 422 | 100.0% | 86.3% | 区間利用可 |
| ダート | 1400-1799m | 600 | 100.0% | 66.7% | 3Fペアのみ |
| ダート | 1800-2199m | 597 | 100.0% | 86.8% | 区間利用可 |
| ダート | 2200m以上 | 19 | 100.0% | 89.5% | 標本不足 |
| 芝 | 1399m以下 | 313 | 100.0% | 99.7% | 区間利用可 |
| 芝 | 1400-1799m | 511 | 100.0% | 95.9% | 区間利用可 |
| 芝 | 1800-2199m | 671 | 100.0% | 100.0% | 区間利用可 |
| 芝 | 2200m以上 | 196 | 100.0% | 93.4% | 最低件数に4件不足 |

- 確定前行1,381件、JRA平地外・解析不能121件を除外し、重複行は0件だった。
- S3+L3は主要距離帯ですべて100%のため、v4候補の入力として利用可能。
- 区間ラップはダート1400-1799mで欠損が多く、初期v4の必須特徴量にはしない。

### 未完了・作業が止まっている箇所

- API側`races`は`rpci_actual`だけを保存し、取り込み時に受け取る`race_s3f`・`race_l3f`を保持していない。
- このままではmykeibadbの利用可能な3F履歴を学習・オンライン予測で同じ条件から再生成できない。
- v4実装前に、`Race`・`RaceModel`・Repository・ingest resultsへS3/L3を追加し、
  Alembic migrationと直近1年のresults再同期を行う必要がある。

### 次に実施する具体的な手順

1. `apps/api/src/pci/domain/racing/race.py`と
   `apps/api/src/pci/infrastructure/database/models.py`へ内部用`race_s3f`・`race_l3f`を追加する。
2. Alembic migrationを追加し、`race_repository.py`の保存・復元と
   `RecordRaceResultsUseCase.execute()`の更新経路をテストする。
3. ingest契約テストでS3/L3の保存を確認し、画面・公開Race DTOには追加しない。
4. mykeibadbの直近1年を`--step results`で再同期し、非NULL率を診断する。
5. `train_rpci_lgbm.py`へ対象日より前のS3/L3履歴特徴量をv4として追加し、独立200レースで比較する。

### 仮実装・暫定値・未確定仕様・既知事項

- 最低200レース・カバー率80%は診断用の可変条件であり、正式なモデル採用基準ではない。
- 距離帯4区分は既存RPCI v2特徴量と揃えた診断単位であり、最適化済みではない。
- 区間完全性は`ceil(distance_m / 200)`個の連続ラップが揃うことを暫定定義としている。
- 全体Ruffは既存`windows_client.py`・`locate_corners.py`など14件、
  全体mypyは既存`windows_client.py`・`mykeibadb_client.py`20件で失敗する。
- Codex領域ではpytestキャッシュ作成警告が1件出る。

### テスト実行コマンドと結果

```powershell
cd apps\ingestion-worker
$env:PYTHONPATH='src'
python -m pytest -q
# 237 passed
python -m ruff check src\ingestion\diagnose_lap_coverage.py `
  tests\test_diagnose_lap_coverage.py
# passed
python -m mypy src\ingestion\diagnose_lap_coverage.py --strict
# passed
python -m ingestion.diagnose_lap_coverage --date 20250724 --date-to 20260723 `
  --min-races 200 --min-coverage 0.8
```

### Claude Codeが最初に確認するファイル

1. `apps/ingestion-worker/src/ingestion/diagnose_lap_coverage.py`
2. `apps/ingestion-worker/tests/test_diagnose_lap_coverage.py`
3. `apps/api/src/pci/domain/racing/race.py`
4. `apps/api/src/pci/application/race_use_cases.py`
5. `apps/api/src/pci/infrastructure/repositories/race_repository.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\ingestion-worker
$env:PYTHONPATH='src'
python -m pytest tests\test_diagnose_lap_coverage.py -q
python -m ingestion.diagnose_lap_coverage --date 20250724 --date-to 20260723
```

## 2026-07-24 10:15 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `68a4e78`
- 実装コミット: `6993999`
- 目的: 予測時点より前の各馬の前付けペース履歴をRPCI v3候補へ追加し、独立期間で採否を判断する。

### 完了した内容

- `apps/api/src/pci/application/forecast_use_cases.py`
  - 全出走馬について、過去最大10走から1角2番手以内（1角欠損時は4角）で運んだ走りを抽出する。
  - PCIを優先し、欠損時は同レースRPCIを使って馬単位の平均と標本数を生成する。
  - 既存rule-v2用の`front_pace_samples`とは分離し、新しい`field_front_pace_samples`だけへ格納する。
- `apps/api/src/pci/domain/pace/rpci_forecast.py`
  - `RaceContext.field_front_pace_samples`を追加した。既定値は空で、既存呼び出しと互換である。
- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
  - v2の27特徴量へ、履歴保有馬数・標本数・平均PCI・最小PCI・馬間の幅・カバー率を加えた
    33特徴量の`FEATURE_NAMES_V3`を追加した。
  - 特徴量数からv1/v2/v3を自動判別し、芝・ダートそれぞれのv3モデル世代を記録する。
- `apps/api/scripts/train_rpci_lgbm.py`
  - `--feature-set v3`を追加した。明示的な`--output`がない場合は本番モデル保護のため終了する。
  - LATERAL JOINで各出走馬の対象日より前の前付け履歴を最大10走集約する。
  - `pr.race_date < r.race_date`を必須条件とし、対象レースと未来レースを学習特徴量へ含めない。
- 単体テストで全脚質からの履歴抽出、既存rule-v2との分離、v3特徴量値・世代判定、
  学習SQLの時点条件と保存先必須を検証した。

### 実DB診断と採用判断

- 芝v3（独立200レース）:
  - MAE`4.298`（現行`5.625`）、展開一致率`58.5%`（現行`63.5%`）。
  - ハイ`58.3%`、平均`40.0%`、スロー`66.2%`。
  - PAI相関`-0.001`、最上位帯リフト`1.12x`。
- ダートv3（独立200レース）:
  - MAE`2.609`（現行`5.401`）、展開一致率`65.0%`（現行`35.5%`）。
  - ハイ`0%`、平均`58.5%`、スロー`75.0%`。
  - PAI相関`+0.006`、最上位帯リフト`1.19x`。
- 回帰誤差、平均・スロー、順位系指標には改善があるが、芝の総合一致率とハイ再現率が悪化し、
  ダートのハイを一度も再現できないため不採用とした。候補モデル3件は削除し、本番v1モデルを維持した。

### 未完了・作業が止まっている箇所

- v3の学習・推論基盤は完成したが、本番v3モデルは存在しない。
- ダートのハイ再現率0%が継続している。単純な前付けPCI集約だけでは展開の上側を説明できない。
- 次回は`train_rpci_lgbm.py`へ前半3F・区間ラップの履歴を追加する前に、
  mykeibadb由来のラップ欠損率と距離別の利用可能件数を診断する。

### 仮実装・暫定値・未確定仕様・既知事項

- 1角2番手以内、最大10走は候補比較用の暫定定義であり、最適化済みではない。
- PCI欠損時のRPCI代替も暫定仕様。馬固有値とレース全体値の混在影響を次回診断する。
- v3特徴量は内部計算専用で、PCI/RPCI実数値を画面へ表示しない。
- `ruff check src tests scripts`の既存`scripts/seed_dev.py`10件と、Codex領域のpytestキャッシュ警告は継続。

### テスト結果

- 対象: 83 passed
- `python -m pytest -m "not integration" -q`: 569 passed、28 deselected
- 変更対象Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 64 files passed
- Web変更なしのためWeb typecheck/buildは未実行

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/application/forecast_use_cases.py`の`_build_field_front_pace_sample`
2. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`の`FEATURE_NAMES_V3`と`build_features`
3. `apps/api/scripts/train_rpci_lgbm.py`の`_HISTORY_JOIN`
4. `apps/api/tests/unit/test_train_rpci_lgbm.py`
5. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\application\test_forecast_use_cases.py `
  tests\unit\infrastructure\pace\test_lgbm_forecaster.py `
  tests\unit\test_train_rpci_lgbm.py -q
python -m scripts.backtest_forecast --track-type dirt --limit 200 --rpci-min 20 --rpci-max 90
```

## 2026-07-24 09:26 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `ee9492d`
- 実装コミット: `7480178`
- 目的: 予測時点で利用できるレース構成・距離・競馬場特徴量をRPCI候補へ追加し、v1互換を維持して比較する。

### 完了した内容

- `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
  - 既存8特徴量を`FEATURE_NAMES`として維持し、27特徴量の`FEATURE_NAMES_V2`を追加した。
  - v2は出走頭数、逃げ比率、逃げ・先行頭数、自在比率、2頭目以降の逃げ競合比率、
    距離4帯、JRA10場one-hotを含む。
  - モデルの`num_feature()`からv1/v2を選択し、芝v2・ダートv1のような混在も扱える。
  - 8/27以外の特徴量数はロード時に拒否し、誤ったベクトルで予測しない。
  - v2モデルは`lgbm-v2-features`、`lgbm-turf-v2-features`、
    `lgbm-dirt-v2-features`として結果へ記録する。
- `apps/api/scripts/train_rpci_lgbm.py`
  - SQLへv2特徴量を追加し、`--feature-set v1|v2`で学習列を選択可能にした。
  - v2では`--output`を必須とし、追跡中の本番v1モデルを誤上書きできない。
- 単体テストでv2の値・順序・距離帯・one-hot・モデル自動判別・未知スキーマ拒否・
  世代記録・保存先必須を検証した。

### 実DB診断と採用判断

- 芝v2（独立200レース）:
  - MAE`4.397`（現行`5.625`）だが、展開一致率`56.5%`（現行`63.5%`）。
  - ハイ`59.4%`、平均`36.7%`、スロー`60.8%`。平均は現行`23.3%`から改善したが、
    ハイと総合一致率が悪化した。
  - PAI相関`+0.017`（現行`-0.028`）、最上位帯リフト`1.26x`（現行`0.90x`）へ改善した。
- ダートv2（独立200レース）:
  - MAE`2.617`（現行`5.401`）、展開一致率`63.5%`（現行`35.5%`）。
  - 平均`59.6%`、スロー`71.0%`だが、ハイ再現率は`0%`（現行`100%`）。
  - PAI相関`-0.010`、最上位帯リフト`1.19x`。
- 順位系指標と大半の回帰・分類指標には改善があるが、芝の総合悪化とダートのハイ欠落を許容できないため、
  候補モデル2件は不採用・削除した。本番v1モデルは変更していない。

### 未完了・未確定仕様・既知事項

- v2特徴量基盤は候補比較用として利用可能だが、本番v2モデルは存在しない。
- ダートのハイは頻度補正と静的なレース構成特徴量の双方で期間外再現率0%だった。
  次は各馬の過去走から、予想時点より前の前半ラップ傾向や先行争いの質を集約する必要がある。
- ラップ特徴量はlookaheadを避け、対象レースより前の履歴だけから生成する。
  当該レースの確定ラップを入力へ使ってはならない。
- `ruff check src tests scripts`の既存`seed_dev.py`10件と、Codex領域のpytestキャッシュ警告は継続。

### テスト結果

- 対象: 49 passed
- `python -m pytest -m "not integration" -q`: 563 passed、28 deselected
- 変更対象Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 64 files passed
- Web変更なしのためWeb typecheck/buildは未実行

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/infrastructure/pace/lgbm_forecaster.py`
2. `apps/api/scripts/train_rpci_lgbm.py`
3. `apps/api/tests/unit/infrastructure/pace/test_lgbm_forecaster.py`
4. `docs/DECISIONS.md`
5. `tasks/backlog.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\infrastructure\pace\test_lgbm_forecaster.py `
  tests\unit\test_train_rpci_lgbm.py -q
python -m scripts.train_rpci_lgbm --track-type turf --feature-set v2 `
  --output models\rpci_lgbm_turf_v2_candidate.txt
```

## 2026-07-24 01:39 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `7d2beaa`
- 実装コミット: `b5812bc`
- 目的: RPCI回帰モデルの少数展開区分を学習時に補正し、独立期間で採否を判断できるようにする。

### 完了した内容

- `apps/api/scripts/train_rpci_lgbm.py`
  - `--label-balance none|sqrt-inverse|inverse`を追加した。
  - 芝・ダート固有の3区分ごとに、逆頻度平方根または逆頻度のサンプル重みを算出する。
  - 重みは平均1.0へ正規化し、LightGBMの学習データだけへ適用する。検証指標は加重しない。
  - 区分別の学習件数と適用重みを表示する。
  - 加重学習では`--output`を必須とし、既定の本番モデルパスを誤って上書きできない。
- `apps/api/tests/unit/test_train_rpci_lgbm.py`
  - 重みなし、少数区分の加重、コース別グループ、区分総重みの均等化、保存先必須を検証した。

### 実DB診断と採用判断

- 芝`√逆頻度`候補（独立200レース）:
  - MAE `4.310`（現行`5.625`）、総合一致率`63.0%`（現行`63.5%`）。
  - 平均再現率`40.0%`（現行`23.3%`）へ改善したが、ハイは`66.7%`（現行`80.2%`）へ悪化。
  - PAI相関`-0.016`、最上位帯リフト`1.05x`。
- 芝`完全逆頻度`候補（独立200レース）:
  - 平均再現率`43.3%`まで改善したが、総合一致率`55.5%`、スロー再現率`46.0%`へ悪化。
- ダート`√逆頻度`候補:
  - 検証セットでもハイ再現率`0%`のため独立候補から除外した。
- ダート`完全逆頻度`候補:
  - 検証セットではハイ再現率`17.4%`だったが、独立200レースでは`0%`。
  - 独立期間のMAE`3.233`、総合一致率`53.0%`で、期間外再現性を確認できなかった。
- 少数区分の改善と主要区分の悪化が交換条件になり、ダートは期間外でハイを再現できないため、
  4候補とも不採用。本番モデルと既定`none`は維持し、候補ファイルは削除した。

### 未完了・未確定仕様・既知事項

- `tasks/backlog.md`のダート「ハイ」・芝「平均」の構造的課題は継続する。
  ラベル頻度だけでは解消せず、前半ラップ傾向、逃げ競合の質、距離・競馬場の交互作用など
  予測時点で取得できる追加特徴量が必要。
- 採用条件となる区分別再現率の最低値は未確定。今回も全体指標と各区分が同時改善する候補だけを
  採用する保守方針を維持した。
- `ruff check src tests scripts`の既存`seed_dev.py`10件と、Codex領域のpytestキャッシュ警告は継続。

### テスト結果

- `python -m pytest tests/unit/test_train_rpci_lgbm.py -q`: 8 passed
- `python -m pytest -m "not integration" -q`: 553 passed、28 deselected
- 変更対象Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 64 files passed
- Web変更なしのためWeb typecheck/buildは未実行

### Claude Codeが最初に確認するファイル

1. `apps/api/scripts/train_rpci_lgbm.py`
2. `apps/api/tests/unit/test_train_rpci_lgbm.py`
3. `docs/DECISIONS.md`
4. `tasks/backlog.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\test_train_rpci_lgbm.py -q
python -m scripts.train_rpci_lgbm --track-type dirt --label-balance inverse `
  --output models\rpci_lgbm_dirt_candidate.txt
```

## 2026-07-24 00:33 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `95d74a8`
- 実装コミット: `4976e65`
- 目的: RPCI LightGBM学習で失われていた脚質特徴量を復旧し、候補モデルを本番へ影響させず比較できるようにする。

### 完了した内容

- `apps/api/scripts/train_rpci_lgbm.py`
  - DBの正規脚質表記`逃げ`・`先行`・`差し`・`追込`を学習SQLで使用するよう修正した。
  - SQLは最新順を維持し、直近20%を検証、残る古い80%を学習に使うよう時系列分割を修正した。
  - 5レース未満を拒否し、検証セットの芝・ダート別3分類再現率を出力する。
  - `lightgbm` importを実行時へ遅延し、SQL定義をモデル未導入環境でもテスト可能にした。
- `apps/api/scripts/backtest_forecast.py`
  - `--turf-model-path`と`--dirt-model-path`を追加した。
  - 候補モデルを本番ファイルへ上書きせず、既存のas-ofバックテストで比較できる。
- `apps/api/tests/unit/test_train_rpci_lgbm.py`
  - 正規脚質ラベル、最新順、コース別分類閾値を回帰テストで固定した。

### 実DB診断と採用判断

- `race_entries.running_style`は非NULL214,968件がすべて2文字の正規表記で、旧SQLの1文字ラベルは0件だった。
  したがって従来学習では脚質構成特徴量が常にゼロだった。
- 修正版で候補モデルを生成し、直近200レースをas-of条件で比較した。
  - 芝候補: MAE 4.347（現行5.625）だが、分類一致率58.0%（現行63.5%）、
    ハイ再現率58.3%（現行80.2%）へ悪化。
  - ダート候補: MAE 2.655（現行5.401）、分類一致率62.0%（現行35.5%）だが、
    ハイ再現率0%（現行100%）。
  - ダート候補へ現行ハイ判定を合成する試行はMAE 3.404、分類一致率55.5%で、
    候補単体より悪化した。
- 展開3分類の重要な区分を欠落させるため、候補モデルと合成案は不採用。
  候補モデルファイル、実験用合成予測器、一時オプションは削除し、本番モデルは変更していない。

### 未完了・未確定仕様・既知事項

- 正規脚質特徴量を使う本番モデルの採用は未完了。全体精度だけでなく芝・ダート各3区分の
  再現率を満たす学習目標、損失、特徴量を別途検討する必要がある。
- `tasks/backlog.md`のダート「ハイ」・芝「平均」の構造的課題は継続。今回の単純再学習では解消しない。
- `ruff check src tests scripts`は、今回未変更の`apps/api/scripts/seed_dev.py:281`と`:307`にある
  未使用ループ変数・行長の既存10件で失敗する。変更対象Ruffは成功している。
- pytest警告はCodexワークスペースの`.pytest_cache`書込権限のみ。

### テスト結果

- `python -m pytest -m "not integration" -q`: 548 passed、28 deselected
- `python -m pytest tests/unit/infrastructure/pace/test_lgbm_forecaster.py tests/unit/test_train_rpci_lgbm.py -q`:
  34 passed
- 変更対象Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 64 files passed
- Web変更なしのためWeb typecheck/buildは未実行

### Claude Codeが最初に確認するファイル

1. `apps/api/scripts/train_rpci_lgbm.py`
2. `apps/api/scripts/backtest_forecast.py`
3. `apps/api/tests/unit/test_train_rpci_lgbm.py`
4. `tasks/backlog.md`
5. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests\unit\test_train_rpci_lgbm.py -q
python -m scripts.backtest_forecast --track-type ダート --limit 200 `
  --rpci-min 20 --rpci-max 90 --dirt-model-path C:\path\candidate.txt
```

## 2026-07-24 00:06 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `04b0024`
- 実装コミット: `42cd051`
- 目的: PAIで未使用だった距離・馬場係数を、lookaheadのない実履歴へ保守的に接続する。

### 完了した内容

- `apps/api/src/pci/domain/pace/course_aptitude.py`
  - `CourseAptitudeRaceResult`、`CourseAptitudeProfile`、
    `build_course_aptitude_profile()`を追加した。
  - 予想日より前かつ対象と同じ芝/ダートの確定着順だけを使う。
  - 距離は好走2件以上から今回に最も近い距離を採用し、前後200m以内は適合扱いにする。
  - 道悪は今回距離の前後400m、良・道悪各3件以上を必要とし、
    頭数補正した着順評価の差が0.30以上の場合だけ弱点を立てる。
  - 標本不足・無効着順・異なる馬場種別では`None`/`False`へ縮退する。
- `apps/api/src/pci/application/forecast_use_cases.py`
  - `distance_aptitude_m`と`weak_on_off_track`を`HorsePaceProfile`へ接続した。
  - 最大20走を1回読み、脚質5走、前付け10走、ペース相性12走、能力5走、
    コース適性20走で共用する。従来の重複DB照会を除いた。
  - 前付け・ペース相性も予想日より前の履歴に統一し、バックテストの未来参照を防いだ。
- `apps/api/src/pci/domain/pace/adaptability.py`
  - 入力意味が変わるためPAIモデル世代を`pai-v2`へ更新した。
  - Web向け説明は従来どおり内部PCI/RPCI/PAI実数を出さない。
- 単体テストで距離、馬場種別、標本不足、無効着順、距離帯許容、道悪比較、
  ユースケース接続、モデル世代を検証した。

### 実DB診断と採用判断

- 2025-07-01〜2025-12-31、30レース・424頭:
  - 導入後の全体PAI相関 `+0.070`、最上位帯リフト `1.16x`。
  - 導入前は`+0.069`、`1.17x`であり、実質同水準。
  - 芝は`+0.165` / `1.41x`、ダートは`-0.051` / `0.84x`。
- 2026-01-01〜2026-07-23、30レース・413頭:
  - 導入後の全体PAI相関 `-0.069`、最上位帯リフト `0.94x`。
  - 導入前も`-0.069`、`0.94x`で同水準。
  - 芝は`-0.065` / `0.88x`、ダートは`-0.081` / `1.09x`。
- 最初の中央値距離案と距離200m差も減点する案は実DB指標が悪化したため不採用。
  最寄り好走距離と200m許容へ修正し、既存指標を維持したうえで説明根拠を追加した。

### 暫定値・未確定仕様・既知事項

- 好走2件、距離許容200m、馬場比較400m、良/道悪各3件、評価差0.30は暫定値。
  係数を自動最適化した値ではなく、誤判定を抑える保守的な初期値である。
- 2期間60レースは正式な係数最適化には小さい。`pai-v2`を蓄積後、独立期間で再検証する。
- 2026年前半はPAI相関自体が負であり、距離・馬場接続だけでは解消していない。
  `PaiWeights`は今回変更していない。
- 既存`pai-v1` martは自動削除しない。各レースを再予想すると`pai-v2`が保存される。

### テスト結果

- PAI・予想ユースケース対象: 54 passed
- `python -m pytest -m "not integration" -q`: 545 passed、28 deselected
- `python -m pytest tests/integration/test_api_integration.py -q`: 6 passed
- API全体Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 64 files passed
- 実DBバックテストCLI: 2025年30件・424頭、2026年30件・413頭とも完走
- 残る警告はCodexワークスペースの`.pytest_cache`書込権限のみ。

### Claude Codeが最初に確認するファイル

1. `apps/api/src/pci/domain/pace/course_aptitude.py`
2. `apps/api/src/pci/application/forecast_use_cases.py`
3. `apps/api/tests/unit/domain/pace/test_course_aptitude.py`
4. `tasks/current.md`
5. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/domain/pace/test_course_aptitude.py `
  tests/unit/application/test_forecast_use_cases.py -q
python -m scripts.backtest_forecast --date-from 2026-01-01 --date-to 2026-07-23 `
  --limit 30 --sample-every 5 --rpci-min 20 --rpci-max 90
```

## 2026-07-23 23:44 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `0ce72be`
- 実装コミット: `4782895`
- 目的: 暫定`PaiWeights`を本番変更せず、実DBで同一母集団比較できる基盤を追加する。

### 完了した内容

- `apps/api/src/pci/application/backtest.py`
  - `PaiWeightProfile`、`PaiWeightMetrics`、`PaiWeightComparison`を追加した。
  - 現行、`rpci-light/heavy`、`preference-compressed/expanded`の5候補を定義した。
  - `ForecastBacktester`へ`PaceAdaptabilityScorer`注入点を追加した。
  - 同一レース・同一馬を厳密照合し、全体・芝・ダート別のpoint-biserial相関と
    最上位PAI帯リフト、現行差を集計する。
  - `HorseSample.track_type`を追加し、JSON明細でもコース種別を保存する。
- `apps/api/scripts/backtest_forecast.py`
  - `--compare-pai-weights`を追加し、CLIと`--output` JSONへ比較結果を出力する。
  - 現行レポートを再利用し、候補4件だけを追加実行する。本番値は自動変更しない。
- `apps/api/tests/unit/application/test_backtest.py`
  - 芝・ダート差分、対象馬不一致拒否、JSON、CLI表示を検証するテストを追加した。

### 実DB診断と採用判断

- 2025-07-01〜2025-12-31、30レース・424頭:
  - `rpci-light`: 全体相関 +0.006、上位帯リフト +0.052。
  - `preference-compressed`: 全体相関 +0.014、上位帯 +0.125。芝・ダートも両指標が悪化しなかった。
- 2026-01-01〜2026-07-23、30レース・413頭:
  - `rpci-light`: 全体相関 +0.003、上位帯 +0.083。芝相関は -0.001。
  - `preference-compressed`: 全体相関 +0.018、上位帯 +0.040だが、
    ダート上位帯リフトが -0.294。
- 両期間・両コースで全指標を安定改善する候補がなく、2026年は現行PAI相関自体が負だった。
  小標本で本番値を変えず、現行`PaiWeights`を維持する。

### 未完了・既知事項

- `ForecastRaceUseCase`は`HorsePaceProfile.distance_aptitude_m`と`weak_on_off_track`を
  現在設定していない。したがって距離・馬場の`PaiWeights`は実予想で効果を持たず、今回の候補から除外した。
- 距離適性・道悪弱点は過去走からlookaheadなしで構築する別タスク。仕様根拠なしに値を補わない。
- 60レースは正式採用には小さい。比較基盤を使い、より大きな独立期間・開催条件で再検証する。

### テスト結果

- `python -m pytest tests/unit/application/test_backtest.py -q`: 38 passed
- `python -m pytest -m "not integration" -q`: 536 passed、28 deselected
- API全体Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 63 files passed
- 実DBバックテストCLI: 2025年30件、2026年30件とも完走

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/src/pci/application/backtest.py`
3. `apps/api/scripts/backtest_forecast.py`
4. `apps/api/src/pci/domain/pace/adaptability.py`
5. `tasks/backlog.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_backtest.py -q
python -m scripts.backtest_forecast --limit 200 --sample-every 3 `
  --rpci-min 20 --rpci-max 90 --compare-pai-weights
```

## 2026-07-23 23:29 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `3120976`
- 実装コミット: `1b580c6`
- 目的: Starlette TestClientの`httpx`非推奨警告を正式な移行経路で解消する。

### 完了した内容

- ローカルのStarlette 1.3.1実装を確認し、`httpx2`が存在すれば自動的に優先されることを確認した。
- `apps/api/pyproject.toml`の`dev`へ`httpx2>=2.7,<3`を追加した。
- テストコードの`fastapi.testclient.TestClient`利用は変更していない。Starlette側の選択機構を使う。
- アプリ本体のGemini RESTクライアントは従来どおり`httpx`を使い、実行時依存と挙動を変更していない。
- 開発環境では`httpx2 2.9.0`を導入し、`pip check`で依存競合がないことを確認した。

### 未完了・既知事項

- 今回の移行に未完了実装はない。
- `.pytest_cache`書込み警告はCodexワークスペース権限由来で、通常クローンの問題ではない。
- 起動用クローンの既存仮想環境でテストする場合は、`pip install -e ".[dev]"`を一度実行して
  `httpx2`を導入する必要がある。APIサーバーの通常起動だけなら不要。

### テスト結果

- `python -m pytest tests/contract -q`: 90 passed
- `python -m pytest -m "not integration" -q`: 533 passed、28 deselected、1 warning
- `python -m pytest tests/integration/test_api_integration.py -q`: 6 passed
- API全体Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 63 files passed
- `python -m pip check`: no broken requirements

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/pyproject.toml`
3. `apps/api/tests/contract/conftest.py`
4. `apps/api/tests/integration/test_api_integration.py`
5. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
python -m pip install -e ".[dev]"
$env:PYTHONPATH='src'
python -m pytest -m "not integration" -q
python -m pytest tests/integration/test_api_integration.py -q
```

## 2026-07-23 22:53 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `5ce5be7`
- 実装コミット: `7d4e034`
- 目的: APIテストに残る自コード・自設定由来の非推奨警告を解消する。

### 完了した内容

- `apps/api/src/pci/presentation/routers/ingest.py`の4箇所で、Starletteの旧
  `HTTP_422_UNPROCESSABLE_ENTITY`を`HTTP_422_UNPROCESSABLE_CONTENT`へ変更した。
  HTTPステータス値とAPI契約は422のまま変わらない。
- `apps/api/alembic.ini`へ`path_separator = os`を追加し、`prepend_sys_path`の
  旧区切り解釈に関するAlembic警告を解消した。
- API非統合テストの警告は5件から2件へ減少した。

### 未完了・既知事項

- FastAPI 0.138.0 / Starlette 1.3.1のTestClient警告は、この次の更新で`httpx2`を導入して解消済み。
- `.pytest_cache`の書込み警告はCodexワークスペース権限由来。通常クローンでの動作不良ではない。
- 設計判断の変更はないため、今回`docs/DECISIONS.md`への追記は行っていない。

### テスト結果

- `python -m pytest tests/contract/test_ingest_api.py -q`: 42 passed
- `python -m pytest tests/integration/test_database_readiness.py -q`: 2 passed
- `python -m pytest -m "not integration" -q`: 533 passed、28 deselected、2 warnings
- API全体Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 63 files passed

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/src/pci/presentation/routers/ingest.py`
3. `apps/api/alembic.ini`
4. `docs/HANDOFF.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest -m "not integration" -q
python -m pytest tests/integration/test_database_readiness.py -q
```

## 2026-07-23 22:46 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `401f450`
- 実装コミット: `4a45799`
- 目的: API全体テストで発見したログ検証の実行順依存を解消する。

### 完了した内容

- 原因は`tests/integration/test_database_readiness.py`の`integration`マーカー漏れだった。
  `pytest -m "not integration"`でも同テストが実行され、Alembicの`fileConfig`が既存の
  `pci.*`ロガーを無効化したため、後続3テストの`caplog`が空になっていた。
- 同テストへモジュール単位の`pytest.mark.integration`を追加した。
- `apps/api/alembic/env.py`で`disable_existing_loggers=False`を指定し、管理CLIやテストから
  同一プロセスでマイグレーションを呼んでもアプリロガーを保持するようにした。
- マイグレーション前から存在するロガーが実PostgreSQLへの適用後も有効であることを
  `test_migration_keeps_existing_application_loggers_enabled`で固定した。

### 未完了・既知事項

- 今回の修正に未完了実装はない。
- pytestキャッシュはワークスペース権限により作成できず警告が出るが、結果には影響しない。
- Starlette/httpxとHTTP 422定数の非推奨警告は、後続更新で解消済み。

### テスト結果

- `python -m pytest -m "not integration" -q`: 533 passed、28 deselected
- `python -m pytest tests/integration/test_database_readiness.py -q`: 2 passed
- 変更対象Ruff: passed
- `python -m mypy src --strict --python-version 3.12`: 63 files passed

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/alembic/env.py`
3. `apps/api/tests/integration/test_database_readiness.py`
4. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest -m "not integration" -q
python -m pytest tests/integration/test_database_readiness.py -q
```

## 2026-07-23 22:42 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `fa093fa`
- 実装コミット: `fafc133`
- 目的: `RuleWeights`の候補を同一レースで比較し、仮係数を実データで診断できる基盤を追加する。

### 完了した内容

- `apps/api/src/pci/application/backtest.py`
  - `RuleWeightProfile`、`RuleWeightMetrics`、`RuleWeightComparison`を追加した。
  - 現行、`style-light/heavy`、`evidence-light/heavy`の5候補を定義した。
  - `compare_rule_weight_reports()`で候補間の対象レース一致を検証し、全体・芝・ダート別の
    MAE、展開分類一致率、現行差を集計する。
  - `RpciSample.track_type`を追加し、JSON明細でもコース種別を保存する。
- `apps/api/scripts/backtest_forecast.py`
  - `--compare-rule-weights`を追加した。比較時はLightGBMの選択状態に依存せず、
    各候補の`RuleBasedRpciForecaster`を同一対象へ実行する。
  - CLIと`--output` JSONへ比較結果を出力する。本番`DEFAULT_WEIGHTS`は変更しない。
- `apps/api/tests/unit/application/test_backtest.py`
  - 全体・芝・ダート差分、対象不一致拒否、JSON、CLI表示を検証するテストを追加した。

### 実DB診断と採用判断

- 2025-07-01〜2025-12-31、50件（`sample-every=3`）:
  - `evidence-heavy`: 全体MAE -0.198、分類一致率 +4.0pt。
  - 芝MAE -0.068・一致率 ±0.0pt、ダートMAE -0.300・一致率 +7.1pt。
- 2026-01-01〜2026-07-23、30件（`sample-every=5`）:
  - `evidence-heavy`: 全体MAE -0.186、分類一致率 -6.7pt。
  - 芝MAE -0.281・一致率 ±0.0pt、ダートMAE +0.033・一致率 -22.2pt。
- MAE改善は再現したが分類一致率、とくに2026年ダートが悪化したため候補は採用しない。
  `RuleWeights`は現行値を維持する。

### 未完了・既知事項

- `RuleWeights`の正式化は未完了。今回の80件は候補を採用するには小さく、開催場・距離・季節別の
  安定性も未検証。比較基盤を使い、より大きな独立標本で再検証する。
- API全体テストは531 passed・3 failed。失敗は今回の変更外にあるログ文言の`caplog`検証3件で、
  同じ3件を単独再実行すると3 passed。テスト順序によるロガー状態汚染が既知問題。
- `.pytest_cache`はワークスペース権限により作成できず警告が出るが、テスト結果には影響しない。

### テスト結果

- `python -m pytest tests/unit/application/test_backtest.py -q`: 35 passed
- `python -m ruff check src tests scripts/backtest_forecast.py`: passed
- `python -m mypy src --strict --python-version 3.12`: 63 files passed
- `python -m pytest -m "not integration" -q`: 531 passed、3 failed、26 deselected
- 上記失敗3件の単独再実行: 3 passed
- 実DBバックテストCLI: 2025年50件、2026年30件とも完走

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/src/pci/application/backtest.py`
3. `apps/api/scripts/backtest_forecast.py`
4. `apps/api/tests/unit/application/test_backtest.py`
5. `docs/DECISIONS.md`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_backtest.py -q
python -m scripts.backtest_forecast --limit 200 --sample-every 3 `
  --rpci-min 20 --rpci-max 90 --compare-rule-weights
```

## 2026-07-23 22:18 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `4c96177`
- 実装コミット: `9babd33`
- 目的: 不一致レースを条件別に回顧できる予想検証専用画面を追加する。

### 完了した内容

- `GetForecastMissesUseCase`と`ForecastMissesOutput`を追加した。
- `GET /api/v1/forecast-performance/misses`で期間、芝/ダート、予想区分、実績区分、offset/limitを扱う。
- OpenAPIと`@pci/api-client`へ`ForecastMisses`、`ForecastMissQuery`、`getForecastMisses`を追加した。
- `/forecast-review`へURL状態付きフィルター、25件ページング、確定後分析リンクを追加した。
- `ForecastRecentMisses`から「すべての不一致を確認」へ進め、`AppHeader`にも予想検証導線を追加した。
- レース名のプレースホルダー除外を`raceNameOrFallback`へ共通化した。

### 未完了・既知事項

- 今回の機能に未完了実装はない。
- ブラウザー連携のローカル接続エラーにより目視スクリーンショット確認は未実施。Webの型検査と
  production buildは成功している。
- `python -m lint_imports`は実行環境に`lint_imports`が無く起動できなかった。Ruffとmypy strictは成功。
- 検索は最大180日をアプリケーション層で絞り込む。データ量増加時はSQLページングへ移す。

### テスト結果

- API単体・契約・OpenAPI: 21 passed
- API Ruff: passed
- API mypy strict: 63 files passed
- api-client typecheck: passed
- Web: 81 passed、typecheck passed、production build passed
- import-linter: 未実行（`No module named lint_imports`）
- 画面目視: 未実行（ブラウザー連携のローカル接続エラー）

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `apps/api/src/pci/application/forecast_performance_use_cases.py`
3. `apps/api/src/pci/presentation/routers/status.py`
4. `apps/web/src/app/forecast-review/page.tsx`
5. `apps/web/src/lib/forecastReview.ts`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_forecast_performance_use_cases.py `
  tests/contract/test_status_api.py tests/contract/test_openapi_snapshot.py -q
cd ..\..\apps\web
npm test
npm run typecheck
```

## 2026-07-23 22:01 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `55ec4f9`
- 実装コミット: `86067e9`
- 目的: 予想検証の集計から、具体的な不一致レースの回顧へ移動できるようにする。

### 完了した内容

- `PredictionEvaluationRecord`へ競馬場・距離・レース名を追加し、既存の評価クエリで取得するようにした。
- `GetForecastPerformanceUseCase._build_recent_misses`で選択期間内の不一致を最新順に最大5件返す。
- `ForecastMissSchema`とOpenAPI/api-client型を追加した。PCI/RPCI実数値と生の信頼度は返さない。
- `ForecastRecentMisses.tsx`を追加し、予想区分・実績区分と確定後分析へのリンクを表示する。
- `tasks/current.md`に残っていた完了済み重複統合タスクの未完了表記を修正した。

### 未完了・既知事項

- 今回の機能に未完了実装はない。
- 不一致一覧は最大5件固定で、検索・ページングは未実装。必要になった段階で専用画面へ分離する。
- 実JV-Dataオフセット検証、Webhook実地確認、暫定定数の正式化は引き続き外部条件または仕様確定待ち。

### テスト結果

- API単体・契約: 12 passed
- PostgreSQL統合: 1 passed
- API Ruff: passed
- API mypy strict: 63 files passed
- api-client typecheck: passed
- Web: 76 passed、typecheck passed、production build passed

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `tasks/backlog.md`
3. `apps/api/src/pci/application/forecast_performance_use_cases.py`
4. `apps/web/src/components/ForecastRecentMisses.tsx`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_forecast_performance_use_cases.py `
  tests/contract/test_status_api.py -q
cd ..\..\apps\web
npm test
```

## 2026-07-23 21:33 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 実装最新コミット: `fd8592b`
- 目的: 予想martを持つ最後の重複1組を、安全な代替確認後に統合する。

### 完了した内容

- 重複監査へ`predicted_pace`/`pace_fit`のモデル世代別行数を追加した。
- 正規側に同一展開モデルがあり、各PAI世代が正規出走頭数分そろう場合だけ旧martを代替済みと判定する。
- 2026-02-01東京9Rを再同期・統合し、旧キー`2026020105010109`を削除した。
- 実DB検証: 重複0組。正規キー`2026020105010209`は12頭、展開予想1件、PAI 12件を維持。

### テスト結果

- API対象・PostgreSQL統合43 passed
- worker mart判定7 passed
- API/worker Ruff、API mypy strict、worker変更対象mypy strict成功
- api-client typecheck成功
- APIレスポンス変換回帰42 passed

### 未完了

- 重複レース統合タスクに未完了事項はない。
- 次の優先候補は`tasks/backlog.md`の未完了P2/P1から選定する。

## 2026-07-23 20:58 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 実装最新コミット: `0523039`
- 目的: dry-run済み重複レースを正規キーへ安全に統合する。

### 完了した内容

- `DeleteDuplicateRaceUseCase`と`POST /internal/ingest/duplicate-races/delete-stale`を追加。
- `ingest_results`の旧キー削除を正規出走表・成績登録後へ移動。失敗組は旧キーを保持する。
- `reconcile_duplicate_races.py`を追加。dry-run既定、適用時は対象組数一致を必須化。
- 実DB: 自動統合対象449組を同期し、旧キー449件を削除。失敗0件。重複450組から1組へ削減。

### 未完了・次に実施する具体的な作業

1. 残存組: 2026-02-01東京9R、旧`2026020105010109`、正規`2026020105010209`。
2. 両キーとも12頭・確定12頭、`predicted_pace` 1件、`pace_fit` 12件。
3. 両方に`rule-v4`/`pai-v1`があり正規側が約6秒後に生成済み。旧側は誤った出走馬対応のため、
   `race_repository.py`の監査へモデル世代別martカバレッジを追加し、正規側が完全代替すると
   検証できた場合だけ旧mart破棄を許可する。
4. 処理後に`count_duplicate_race_groups(...) == 0`を確認する。

### テスト結果

- API対象42 passed、PostgreSQL統合1 passed
- worker対象76 passed、worker全体229 passed
- API Ruff・mypy strict成功、worker変更ファイルRuff・mypy strict成功
- OpenAPI 2 passed、api-client typecheck成功
- API非統合全体519 passed / 既知caplog 3 failed

### 最初に確認・実行するもの

1. `tasks/backlog.md`
2. `apps/api/src/pci/application/race_use_cases.py`
3. `apps/ingestion-worker/src/ingestion/reconcile_duplicate_races.py`

```powershell
python -m ingestion.reconcile_duplicate_races --date 2025-07-23 --date-to 2026-07-23
```

## 2026-07-23 20:32 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `9b3ad5f`
- 実装最新コミット: `41a4859`
- 今回の目的: 重複450組を削除する前に、正規キー・内容差・関連martを読み取り専用で監査する。

### 完了した内容

1. `SqlAlchemyRaceRepository.find_duplicate_race_audits`
   - 重複キーごとの状態、頭数、確定頭数、出走馬署名、中核成績署名、
     `predicted_pace`/`pace_fit`件数を一括取得する。
   - 中核成績署名は馬番・着順・時計・上がり・通過順に限定し、馬ID・人気・賞金は含めない。
2. `GET /internal/ingest/duplicate-race-audit`
   - `X-Ingest-Token`必須、`date_from`/`date_to`/`limit`指定の読み取り専用APIを追加した。
   - OpenAPIと`@pci/api-client`の型を同期した。
3. `ingestion.audit_duplicate_races`
   - mykeibadbを31日単位で読み、16桁`RACE_CODE`との一意一致から正規キー候補を決める。
   - 5分類のJSON監査結果を出力し、DB更新・削除はしない。
4. 実DB監査
   - 対象: 2025-07-23〜2026-07-23。
   - mykeibadb取得キー3492件、重複450組、各組の旧キーは1件。
   - `removable_after_resync` 450組、その他4分類0組。
   - 全450組で出走馬構成差を検出。旧キーを削除する前に正規キー再同期が必須。

### 未完了・作業が止まっている箇所

- 旧キーの削除・FK移行は未実装。監査で安全条件を確定した段階で止めている。
- 次工程では正規キーをmykeibadbから再同期し、`races`/`race_entries`の頭数・確定頭数を照合してから、
  同一トランザクションで旧キーを削除する必要がある。
- `result_conflict`、`canonical_incomplete`、`source_unresolved`、
  `mart_migration_required`は自動削除対象にしない。

### 次に実施する具体的な手順

1. `apps/ingestion-worker/src/ingestion/audit_duplicate_races.py`の分類結果を入力にする、
   明示的な`--apply`ではなく別コマンドの統合CLIを設計する。
2. `apps/api/src/pci/presentation/routers/ingest.py`へ認証付き統合エンドポイントを追加し、
   `SqlAlchemyRaceRepository`で正規キー再同期後の頭数・確定頭数・mart件数を再検証する。
3. `RaceEntryModel`、`PredictedPaceModel`、`PaceFitModel`の件数が監査値と一致する場合だけ、
   1重複組ずつトランザクションで旧キーを削除する。例外時は組単位でrollbackする。
4. `TestFindDuplicateRaceGroups`と新規契約テストへ、成功・中核成績不一致・martあり・正規キー未確定・
   再同期後頭数不一致のケースを追加する。
5. 実行後に`count_duplicate_race_groups(...) == 0`、レース減少450件、
   正規キー側の確定頭数維持、予想mart件数維持を検証する。

### 仮実装・暫定値・未確定仕様

- 監査期間のCLI既定は365日、mykeibadb読取チャンクは31日。運用値であり正式要件ではない。
- 正規キー再同期後の削除API契約、失敗時の再開単位、監査JSONの再利用可否は未確定。
- 今回の実DBではmart移行対象0件だが、将来の`mart_migration_required`処理方針は未確定。

### 既知の問題

- API非統合テスト全体は516 passed / 3 failed。既存の`caplog`ログ捕捉テスト3件が、
  この実行環境ではログを受け取れず失敗する。今回の変更対象テストは成功。
- worker仮想環境の`mypy`は`librt.internal`欠落で起動不能。システムPython 3.12では
  変更2ファイルのstrict型チェックが成功した。
- 実運用cloneの既存未追跡`apps/ingestion-worker/.env]`と`result_run.txt`には触れていない。

### テスト実行コマンド・結果

- API Ruff: `python -m ruff check src tests scripts/export_openapi.py scripts/backtest_forecast.py`
  -> passed
- API mypy: `python -m mypy src --strict --python-version 3.12` -> 63 files passed
- 対象API/DB: `python -m pytest tests/unit/infrastructure/test_race_repository_audit.py
  tests/contract/test_ingest_api.py tests/integration/test_race_repository.py::TestFindDuplicateRaceGroups -q`
  -> 41 passed
- OpenAPI契約: `python -m pytest tests/contract/test_ingest_api.py
  tests/contract/test_openapi_snapshot.py -q` -> 41 passed
- worker: `python -m pytest tests/test_audit_duplicate_races.py -q` -> 5 passed
- worker全体: `python -m pytest -q` -> 225 passed
- api-client: `npm run typecheck --workspace=@pci/api-client` -> passed
- API非統合全体: 516 passed / 3 failed（上記既知のログ捕捉テスト）

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `tasks/backlog.md`
3. `docs/HANDOFF.md`
4. `docs/DECISIONS.md`
5. `apps/ingestion-worker/src/ingestion/audit_duplicate_races.py`
6. `apps/api/src/pci/infrastructure/repositories/race_repository.py`
7. `apps/api/src/pci/presentation/routers/ingest.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/infrastructure/test_race_repository_audit.py `
  tests/contract/test_ingest_api.py `
  tests/integration/test_race_repository.py::TestFindDuplicateRaceGroups -q
cd ..\ingestion-worker
python -m pytest tests/test_audit_duplicate_races.py -q
```

## 2026-07-23 19:57 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `58f8651`
- 実装最新コミット: `87b5495`
- 今回の目的: 旧形式キーと正規キーが併存する重複レースを、安全に削除できる前段階として継続監視する。

### 完了した内容

1. API/Repository
   - 直近365日のJRA平地を、開催日・競馬場・R番号で集計する読み取りポートを追加した。
   - `/api/v1/ingest-status`へ`has_duplicate_races`、組数、代表20組と各レースキーを追加した。
2. Web
   - `IngestStatusBanner`へ重複レース詳細を追加し、各キーの予想画面へ遷移可能にした。
   - 重複だけがある場合は独立した警告を表示し、他の取り込み異常がある場合も詳細に併記する。
3. 実DB確認
   - 2025-07-23〜2026-07-23で450組を検出した。
   - 自動削除・自動統合は行っていない。

### 未完了・次に実施する作業

1. **P1 重複450組の安全な統合設計**
   - mykeibadbに存在するキーを正規候補とする。
   - `RaceEntryModel`、`PredictedPaceModel`、`PaceFitModel`等の関連件数をdry-runで出力する。
   - 成績・頭数・出走馬が不一致の組を自動対象から除外する。
   - トランザクション内でFKを正規キーへ移行し、移行前後の件数を照合してから旧キーを削除する。
2. **P2 実JV-Dataの人気・賞金予約オフセット検証**
   - `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md`に従い、Windows JV-Link実機で確認する。
3. **P2 暫定定数の検証**
   - 対象定数と受入指標を先に決め、実データで検証する。独断で正式化しない。
4. **P2 Webhook通知の実地確認**
   - Windows実行機で`NOTIFY_WEBHOOK_URL`を設定して失敗通知の到達を確認する。

### 既知の問題

- 重複450組は監視のみで、一覧・バックテスト母集団からまだ除去されていない。
- API全scriptsのRuffは既存`seed_dev.py`の未使用変数・行長10件で失敗する。
  今回の`src`・`tests`・運用scripts対象Ruffは成功した。
- 実運用cloneの既存未追跡`apps/ingestion-worker/.env]`と`result_run.txt`には触れていない。

### テスト結果

- API単体・契約・OpenAPI: 23 passed
- PostgreSQL統合: `TestFindDuplicateRaceGroups` 1 passed
- API Ruff対象範囲: passed
- API mypy strict: passed（63 source files）
- import-linter: 2 contracts kept / 0 broken
- Web: 76 passed
- api-client / Web typecheck: passed
- Web production build: passed

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `tasks/backlog.md`
3. `docs/HANDOFF.md`
4. `apps/api/src/pci/infrastructure/repositories/race_repository.py`
5. `apps/api/src/pci/application/ingest_status_use_cases.py`
6. `apps/web/src/components/IngestStatusBanner.tsx`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_ingest_status_use_cases.py `
  tests/contract/test_status_api.py tests/contract/test_openapi_snapshot.py -q
cd ..\..\apps\web
npm test
```

## 2026-07-23 19:42 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `d946adb`
- 実装最新コミット: `6fda136`
- 今回の目的: 馬場情報バックフィル後の実DBで小倉芝1200mを馬場状態別に再検証し、参考表示の妥当性を確定する。

### 完了した内容

1. `apps/api/src/pci/application/backtest.py`
   - 脚質別有利度の内訳へ`distance-track-condition`を追加した。
   - `1200m / 良`のようなラベルと、距離・馬場状態順の安定した並びを実装した。
2. `apps/api/scripts/backtest_forecast.py`
   - `--style-breakdown distance-track-condition`を選択可能にした。
3. `apps/api/src/pci/domain/pace/style_advantage.py`
   - 7月小倉芝1200mの参考理由へ「馬場状態別でも同じ傾向」を追記した。
   - 参考条件、スコア、PAI、順位、仮係数は変更していない。
4. 実DB再検証
   - 対象: 2025-07-01〜2026-07-31、小倉芝199レース・1534頭。
   - 1200m: 良-22.4pt（45R）、稍重-10.5pt（12R）、重-9.0pt（6R）、不明-26.4pt（27R）。
   - 確認できた全馬場状態で逆転方向が続いたため、`style-advantage-v3`の参考条件を維持した。
   - 1800m・2000mは馬場状態ごとに正負が混在し、参考範囲を拡張する根拠はなかった。

### 未完了・既知の問題

- 今回のタスクに未完了実装はない。
- 「不明」27レースは主に直近365日の補完開始より前の2025年データを含む。今回の既知馬場3区分が
  すべて同方向のため判断は可能だが、監視窓より前まで再補完する場合は同じコマンドで再診断する。
- `StyleAdvantageWeights`は引き続き仮係数。今回の結果だけで反転・補正しない。
- API非統合テスト全体の既知状態は509 passed / 3 failed。失敗は既存のcaplogログ捕捉テストで、
  今回の対象テスト49件は成功した。
- 実運用cloneの既存未追跡`apps/ingestion-worker/.env]`と`result_run.txt`には触れていない。

### テスト結果

- API対象:
  `python -m pytest tests/unit/application/test_backtest.py tests/unit/domain/pace/test_style_advantage.py -q`
  -> 49 passed
- API Ruff: `python -m ruff check src tests scripts/backtest_forecast.py` -> passed
- API mypy: `python -m mypy src --strict --python-version 3.12` -> passed（63 source files）
- import-linter: `lint-imports.exe` -> 2 contracts kept / 0 broken
- 実DB診断:
  `python -m scripts.backtest_forecast --validate-style-advantage --track-type 芝 --venue-code 10
  --date-from 2025-07-01 --date-to 2026-07-31 --style-breakdown distance-track-condition`
  -> 199レース・1534頭を集計、正常終了

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`
3. `docs/SPEC.md`
4. `docs/DECISIONS.md`
5. `apps/api/src/pci/application/backtest.py`
6. `apps/api/src/pci/domain/pace/style_advantage.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
cd apps\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_backtest.py tests/unit/domain/pace/test_style_advantage.py -q
python -m scripts.backtest_forecast --validate-style-advantage --track-type 芝 --venue-code 10 `
  --date-from 2025-07-01 --date-to 2026-07-31 --style-breakdown distance-track-condition
```

## 2026-07-23 19:31 JST OpenAI Codex 更新

- 作業担当: OpenAI Codex
- 引き継ぎ先: Claude Code
- ブランチ: `claude/sweet-einstein-ilnaov`
- 作業開始コミット: `48ddac3`
- 実装最新コミット: `dfcb0d7`
- 今回の目的: 予想検証サマリーの左右見切れを解消し、ほとんどのレースで欠けていた馬場情報を実データから補完する。

### 完了した内容

1. `apps/web/src/components/ForecastPerformanceSummary.tsx`
   - セクションへ `px-4 sm:px-6` を追加し、見出し・期間切替・指標の左右余白を確保した。
2. `apps/ingestion-worker/src/ingestion/batch.py`
   - `includes_race_metadata()` を追加し、mykeibadb の `--step all` でも補足情報を取り込むようにした。
3. `apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`
   - entries後にrace-metadataを自動実行し、終了コードも全体成否へ含めた。
4. `apps/api/src/pci/application/race_use_cases.py`
   - コース種別・馬場状態・天候を更新する。
   - 正規キーと旧キーが併存する場合、日付・競馬場・R番号が一致する重複レースも同時更新する。
   - 正規キーがない場合は候補が一意のときだけ旧キーを更新し、曖昧な候補は更新しない。
5. `apps/ingestion-worker/src/ingestion/parser/common.py`
   - mykeibadb `track_code` マスタに基づき、TrackCDを芝10〜22、ダート23〜29、障害51〜59へ修正した。
6. 実データ補完
   - 2025-07-23〜2026-07-23を3回検証しながら再補完した。最終全期間実行ログはingest log id=55、12月6日再補完はid=56。
   - 未反映件数は564件から0件。
   - `2026020108010111` は芝・良・曇、`2026071902011211` は芝・重・晴を確認。
   - mykeibadbに存在しない開発用シード `2026061805010101` は内部削除APIで削除した。

### 未完了・既知の問題

- 旧形式キーと正規キーの重複レース自体は残っている。今回は削除・成績統合をせず、馬場情報だけを一致させた。重複整理は別タスクとして、RaceEntry・予想マート等のFK移行設計を先に行うこと。
- API非統合テスト全体は509 passed / 3 failed。失敗は既存のcaplogログ文言取得テスト3件で、今回の対象テスト63件は成功。
- ingestion-worker全体lintは既存14件で失敗する。対象は未変更の `windows_client.py`、`locate_corners.py`、`test_locate_corners.py`。今回変更ファイルのlintは成功。
- 作業用workspaceからユーザーの `.venv` を直接起動するとプロセス生成に失敗したため、テストはシステムPython 3.12で実行した。実運用cloneの `run_batch.ps1` は成功している。
- `C:\Users\yuuta\PCI_app\apps\ingestion-worker\.env]` と `result_run.txt` は既存未追跡ファイルのため触れていない。

### テスト結果

- ingestion-worker: `python -m pytest -q` -> 220 passed
- ingestion-worker変更ファイル: Ruff -> passed
- API対象: `pytest tests/unit/application/test_race_use_cases.py tests/contract/test_ingest_api.py -q` -> 63 passed
- API: Ruff -> passed
- API: mypy strict Python 3.12 -> passed (63 source files)
- Web: Vitest -> 74 passed
- api-client / Web: typecheck -> passed
- Web: `next build` -> passed
- API非統合全体: 509 passed / 3 failed（既存ログ捕捉テスト）

### Claude Codeが最初に確認するファイル

1. `tasks/current.md`
2. `docs/HANDOFF.md`
3. `docs/DECISIONS.md`
4. `apps/api/src/pci/application/race_use_cases.py`
5. `apps/ingestion-worker/src/ingestion/parser/common.py`
6. `apps/ingestion-worker/src/ingestion/batch.py`

### Claude Codeが最初に実行するコマンド

```powershell
git status --short --branch
Invoke-RestMethod http://localhost:8000/api/v1/ingest-status
cd apps\ingestion-worker
python -m pytest -q
cd ..\api
$env:PYTHONPATH='src'
python -m pytest tests/unit/application/test_race_use_cases.py tests/contract/test_ingest_api.py -q
```

> Claude Code / Codex を交互に使うための引き継ぎファイル。**作業を中断・終了するたびに更新する。**
> 会話履歴が無くても、このファイル + Git 履歴 + `docs/` + `tasks/` から状態を復元できることが目標。

---

## メタ情報

| 項目 | 値 |
|---|---|
| 更新日時 | 2026-07-23（更新40回目・Codex が予想検証の前期間比較を実装） |
| 作業担当AI | OpenAI Codex |
| 引き継ぎ先 | Claude Code |
| 直前の担当AI | OpenAI Codex（予想検証を直前の同期間と比較可能にした） |
| ブランチ | `claude/sweet-einstein-ilnaov` |
| 最新コミット | `HEAD`（本セッションのコミット。作業開始時は `ed04a84`） |
| 作業ツリー | 本セッションのコミット・push後にクリーン化する前提 |

---

## 現在の作業目的

**選択した展開予想の検証期間を、その直前にある同じ日数と比較し、
全体・芝・ダートの変化を判断できるようにした。**

`GetForecastPerformanceUseCase`は現在期間の直前にある同じ日数を前期間として追加取得する。
期間同士は重複せず、30日なら直近30日対その直前30日、180日なら直近180日対その直前180日となる。
`previous_period`は前期間の日付範囲と全体・芝・ダートの一致率・的中数・母数を必須で返す。
比較元0件の場合も期間と3グループを返し、各一致率だけをnullとする。PCI/RPCI実数値は公開しない。

`ForecastPerformanceSummary`は各指標の下へ前期比をパーセントポイントで表示する。
正は上向きアイコンと緑、負は下向きアイコンと黄、差なしは横線と灰色を使い、符号も併記する。
前期間0件は「前期比較なし」とし、恣意的な改善・悪化の閾値は導入していない。

`GET /api/v1/forecast-performance`は`days=30|90|180`を受け付け、未指定時は90日を使う。
一致率、芝・ダート、信頼度別集計、混同行列、検証カバー率は選択期間で再集計する。
`weekly_trend`だけは期間に連動させず、比較軸を揃えるため常に直近8完了週を返す。
application層は30日選択時も8週分を取得し、期間集計用レコードと週次用レコードを分離する。

Webトップの`ForecastPerformanceSummary`へ30日・90日・180日のセグメントを追加した。
`performance_days`と`date`をURLへ保持し、期間と開催日のどちらを先に変更しても他方の選択を失わない。
不正な`performance_days`はWebで90日に戻し、APIの不正な`days`は422となる。

`MartRepository.find_prediction_evaluations()`は、JST基準の指定期間にある確定済みJRA平地から、
レース日以前に生成された最新の予想を1件だけ選ぶ。application層で確定RPCIを展開区分へ変換し、
全体・芝・ダートの一致率、的中数、母数を集計する。公開
`GET /api/v1/forecast-performance`と`ForecastPerformanceSummary`は期間と集計結果だけを扱い、
PCI/RPCIの内部実数値をAPI・画面へ露出しない。`weekly_trend`は進行中の週を除き、
直近8完了週を月曜から日曜の固定区間で返す。WebはRechartsの棒グラフと最新週の母数を表示し、
完了週のデータがない場合は空グラフを出さない。

`confidence_groups`は既存の`confidenceInsight()`と同じ境界を使い、70%以上を「読みやすい」、
50%以上70%未満を「標準」、50%未満を「変動注意」として一致率・的中数・母数を返す。
`ForecastConfidenceCalibration`は3本の横棒と母数を表示する。信頼度別集計は複数モデル世代を
横断するため、個別モデルの校正指標ではなく現在の画面表示全体の実績として解釈すること。

`pace_matrix`は「速い・平均・落ち着く」の予想3区分を行、実績3区分を列として、
各セルの件数と行内割合を返す。`ForecastErrorPattern`はトップ画面の情報密度を抑えるため
native `details`で既定は閉じ、一致セルを緑、不一致セルを黄で表示する。モバイルは
最小幅430pxの表を横スクロールし、文字や数値を縮めすぎない。

`MartRepository.count_prediction_evaluation_candidates()`は、指定期間の確定済みJRA平地かつ
`rpci_actual`を持つレースを、予想martの有無と独立に集計する。APIは`eligible_race_count`と
`coverage_rate = sample_size / eligible_race_count`を返し、対象0件ならnullとする。
`ForecastEvaluationCoverage`は照合済み件数／対象総数を進捗バーで表示し、全件なら緑、
未保存が残る場合は黄とする。任意の品質閾値は導入していない。

`ForecastPerformanceTrend`は約100KBのRecharts依存を持つため、
`ForecastPerformanceTrendLazy`から`next/dynamic`で遅延読み込みする。直接importした試作では
一覧のFirst Load JSが214KBまで増えたが、遅延化後は110KBへ戻った。

今回の検証は対象単体・契約11 passed、OpenAPIスナップショット2 passed、Web 74 passed。
API Ruff、API全体63ファイルのmypy strict、OpenAPI生成、api-client/Web typecheck、
Web production buildは成功し、一覧のFirst Load JSは110KBを維持した。今回はRepositoryを
変更していないためPostgreSQL統合テストとAPI非統合全体は再実行していない。Web workspaceには
lintスクリプトがないため実行不可（Next buildもlintをskipする）。グローバルPythonには
`lint_imports`が未導入のためimport境界チェックも実行不可だが、application/domainの依存方向は
既存構成に従っている。

既知の制約として、レース発走・結果確定時刻をDBに保持していないため、レース当日に終了後生成された
予想は日付比較だけでは除外できない。通常の`--step forecasts`による事前生成を前提とし、時刻列を
導入した場合に厳密化する。コード実装は完了しており、作業が止まっている箇所はない。

Claude Codeが最初に確認するファイル:
`apps/api/src/pci/application/forecast_performance_use_cases.py`,
`apps/api/src/pci/presentation/routers/status.py`,
`apps/api/src/pci/infrastructure/repositories/mart_repository.py`,
`apps/web/src/components/ForecastConfidenceCalibration.tsx`,
`apps/web/src/components/ForecastEvaluationCoverage.tsx`,
`apps/web/src/components/ForecastErrorPattern.tsx`,
`apps/web/src/components/ForecastPerformanceTrend.tsx`,
`apps/web/src/components/ForecastPerformanceTrendLazy.tsx`,
`apps/web/src/components/ForecastPerformanceSummary.tsx`,
`apps/web/src/components/RaceDateCalendar.tsx`,
`docs/DECISIONS.md`。
最初に実行するコマンド:
`git status --short --branch`、
`cd apps/api && set PYTHONPATH=src && python -m pytest tests/unit/application/test_forecast_performance_use_cases.py tests/contract/test_status_api.py -q`、
`npm.cmd run typecheck --workspace=@pci/web`。

### 前タスク（馬場状態欠損監視）

`GET /api/v1/ingest-status`は、従来のバッチ鮮度・成績未取込に加えて、JST基準の直近365日、
開催日前日まで、`status=result`、JRA10場、平地、`track_condition IS NULL`の件数と
新しい順の代表20件を返す。地方・障害・出走前・365日より古いレースは警告対象外。
Webトップの`IngestStatusBanner`は「馬場情報未反映」として別表示し、対象レースの回顧画面と
専用`race-metadata`コマンドへ案内する。`run_batch.ps1`へ`-ChunkDays`を追加したため、
1年分を7日単位で処理できる。

関連API単体・契約15 passed、PostgreSQL統合1 passed、Web 74 passed。
API全体Ruff、mypy strict（62ファイル）、OpenAPI同期、api-client/Web typecheck、Web buildは成功。
API非統合全体は500 passed / 3 failed / 23 deselected。失敗3件は従来からの`caplog`順序依存で、
単独再実行は3 passed。今回変更したテストに失敗はない。

実mykeibadb/PostgreSQLへのバックフィルはこの環境から接続できないため未実行。
Windows実行機でWeb警告に表示されるコマンド、または下記をリポジトリ直下から実行し、
警告が消えることを確認してから馬場状態別の小倉芝1200m診断を再実行する。

```cmd
powershell -ExecutionPolicy Bypass -File apps\ingestion-worker\scripts\run_batch.ps1 -Step race-metadata -Mode mykeibadb -Date 20250723 -DateTo 20260723 -ChunkDays 7
```

前タスクの4パターン診断結果は以下のとおり。

`--diagnose-style-advantage`は予測/実績RPCI × 予測/確定脚質の4パターンを比較し、
`--venue-code`で競馬場別に絞り込める。2025年後半・2026年前半は正方向だったが、2026年7月だけ逆転。
福島は想定RPCIが主因、函館・小倉は確定値同士でも逆転した。短期標本のため本番係数は変更していない。

今回の検証は関連単体31 passed、Ruff成功、API全体62ファイルのmypy strict成功。API非統合全体は
485 passed / 3 failed / 22 deselected。失敗3件は既存のログ捕捉テストで、単独再実行は3 passed。
実DB1レースで`--validate-style-advantage --output`のJSON生成も成功し、一時ファイルは削除済み。

前セッションの検証は関連単体テスト29 passed、Ruff成功、対象2ファイルと
API全体62ファイルのmypy strict成功。API非統合全体は483 passed / 3 failed / 22 deselectedで、失敗3件は
既存のログ捕捉テストが全体実行時だけ`caplog`を取得できないテスト順序依存。3件の単独再実行は全件成功。
今回の変更対象テストに失敗はない。

`/health`はDBに依存しないlivenessとして維持し、`/ready`はDB接続とSQLAlchemy ORMが必要とする
全テーブル・列を検査する。不足時は503と`schema_outdated`を返す。Webは一覧APIが500になった場合だけ
`/ready`を取得し、スキーマ不足なら`python -m alembic upgrade head`、DB停止ならPostgreSQLと
`DATABASE_URL`の確認を案内する。通常表示時の追加通信はない。

実DBではAlembic 003→004を適用済みで、`/api/v1/races/board?date=2026-07-26`とWebトップの
200応答を確認した。前タスクで`RaceRepository`へ追加した`delete_entries_not_in`を
`_AsOfRaceRepository`にも委譲し、API全体mypyを0エラーへ戻した。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/infrastructure/database/readiness.py`,
`apps/api/src/pci/presentation/routers/health.py`, `apps/web/src/lib/apiError.ts`,
`packages/api-client/src/index.ts`, `docs/DECISIONS.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q`、
`cd ../.. && npm test --workspace=@pci/web`。

テスト結果: API非統合482 passed / 22 deselected、readiness PostgreSQL統合1 passed、関連33 passed、
Web71 passed、API Ruff、API全体mypy strict（62ファイル）、api-client/Web typecheck、Web build成功。
import-linterはローカルPythonに未導入のため未実行。既知の機能不具合はない。

---

### 直前タスク（成績未取り込みと出走馬スナップショット不整合の修復）

根本原因は、特別登録の仮馬番を確定出馬表で完全置換せず、結果だけを馬番で重ねていたこと、
JV障害コードを30番台と誤認していたこと、古い取り込みが誤った開催回・開催日次のレースキーを
生成していたことだった。確定出馬表の完全置換、結果前の出馬表再登録、特別登録の上書き防止、
JRA外・海外・障害の除外、`--only-incomplete`限定修復を実装した。

実DBは未取り込み343件から0件へ修復済み。`2026071910020811`は18頭・17頭着順反映、
`2026071910020801`は障害・11頭へ修正した。限定同期は310レース成功、11レース失敗。
失敗は距離0の海外行または確定出馬表を再構成できない行で、未取り込み警告には残っていない。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/application/race_use_cases.py`,
`apps/api/src/pci/infrastructure/repositories/race_repository.py`,
`apps/ingestion-worker/src/ingestion/batch.py`,
`apps/ingestion-worker/src/ingestion/client/mykeibadb_client.py`, `docs/DECISIONS.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と
`cd ../ingestion-worker && python -m pytest -q`。

未完了・既知事項: SQL統合テストはDocker依存のため今回未実行。worker全体Ruffには既存の
`windows_client.py`、`locate_corners.py`、`test_batch_e2e.py`等の違反が残る。API全体mypyは
Python 3.11設定とローカルNumPy 3.12型定義の不整合で停止するため、変更対象4ファイルだけ成功確認した。

---

### 直前タスク（今後のレース予想の事前生成）

`PrecomputeUpcomingForecastsUseCase`と認証付き`POST /internal/ingest/forecasts/precompute`を追加した。
workerには`--step forecasts`を追加し、`run_mykeibadb_full_sync.ps1`がentries、results、
special-entriesの後に実行する。対象は日本時間の今日以降、`status=entries`、出走馬ありのレースだけ。
過去レースへの後付け予想は行わない。ボードAPIのmart欠損時フォールバックは維持している。

テスト結果: API非統合472 passed、worker全体194 passed、Web68 passed/build成功、API Ruff成功、
変更対象APIのmypy strict、api-client/Web typecheck成功。worker全体Ruffは既存18件、全体mypyは
既存4件（`batch.py`のマスタ変数型）で失敗するが、今回対象のRuffは成功。

Claude Codeが最初に確認するファイル:
`apps/api/src/pci/application/forecast_precompute_use_cases.py`,
`apps/api/src/pci/presentation/routers/ingest.py`,
`apps/ingestion-worker/src/ingestion/batch.py`,
`apps/ingestion-worker/scripts/run_mykeibadb_full_sync.ps1`, `docs/DECISIONS.md`, `tasks/current.md`。
最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と
`cd ../ingestion-worker && python -m pytest tests/test_ingest_api.py tests/test_batch_e2e.py -q`。

未完了・既知事項: 事前生成は同期HTTPリクエスト内で直列実行する（worker側タイムアウトは5分）。
今後レースが大幅に増えて5分を超える場合はジョブキュー化する。ローカル既存DBでは前タスクのmigration適用のため
API起動前に`cd apps/api && alembic upgrade head`が必要。

---

### 直前タスク（取り込みデータ完全性監視）

`GET /api/v1/ingest-status` は従来のバッチ成否・鮮度に加え、日本時間の前日以前で
`races.status=entries` のまま残るレースを集計する。Webトップは件数を警告し、代表20件への
リンクを表示する。取り込みログが無い環境でも、未取込レースがあれば警告する。

暫定条件は「前日以前かつentries」で、当日開催分は除外する。障害競走等の恒常的な誤警告が
確認された場合のみ、対象種別または猶予日数を追加する。現時点で既知の機能不具合はない。

テスト結果: API非統合447 passed、関連SQL integration 1 passed（残り18件は未実行）、Web66 passed、ruff clean、
Web typecheck/build成功。mypyはローカルNumPy型定義がPython 3.11設定で解釈できず依存解析前に停止。

Claude Codeが最初に確認するファイル: `apps/api/src/pci/application/ingest_status_use_cases.py`,
`apps/api/src/pci/infrastructure/repositories/race_repository.py`, `apps/web/src/lib/ingestStatus.ts`,
`tasks/current.md`。最初に実行するコマンド: `git status --short --branch`、続いて
`cd apps/api && python -m pytest -m "not integration" -q` と `npm test --workspace=@pci/web`。

---

### 以前のタスク（AbilityWeights比較CLI）

`--compare-ability-weights`で検証用4候補を同一レース集合に適用し、統合順位の3指標と
現行差をCLI/JSONに出力する。本番重みは書き換えず、実DBでの再現性確認後に別途判断する。

gradeはJRA-VAN公式コードをRA `GradeCD[615]`から読み、ability-v3のクラス補正で優先利用する。
馬体重は既存`race_entries.weight`へ、results単独再取込でも確定値を更新する。体格の大小は能力へ
加点せず、バックテストへ統合順位の比較指標を追加した。

Codex は `tasks/current.md` の最優先候補として「バックテスト結果のJSON保存」に着手し、
ローカルで `144ebfd feat(backtest): export reports as json` を作成した。しかし push 前に
`origin/claude/sweet-einstein-ilnaov` が16コミット進んでおり、その中の `03bc005 feat(backtest):
persist backtest reports to JSON via --output` が同じ目的をより新しい文脈で実装済みだった。
そのため `git merge origin/claude/sweet-einstein-ilnaov` の競合解消では、バックテストJSON保存関連
ファイルと各ドキュメントについて**リモート版を採用**し、後続のClaude Code変更を上書きしない方針にした。
競合マーカーは残っていない。

**直前セッションの要約**: (1) 確定成績未反映の件は**解決**。診断で「解析は正常（453件解析可）」と特定し、
`batch.py`が`record_results`失敗をexit 0に握りつぶしていた欠陥を可視化（件数ログ常設）。ユーザーが
最新コードでresultsステップを再実行→全レース送信成功しアプリに反映。(2) ユーザーが選んだ改善
「**統合順位予想（展開＋能力）**」を Phase1（ability-v1 × integrated-v1）→ ユーザーFB受けてUI刷新
（◎○▲△の印を廃止しタグ＋順位主役へ）→ Phase2（人気・本賞金の永続化でability-v2）まで実装済み。
詳細は下記「完了した作業」0.〜2.、`docs/DECISIONS.md` 2026-07-21（2件）。

（以下は本セッションに至るまでの経緯。）

ユーザーから実利用のフィードバックを受け、2点対応した:
① 展開分析の脚質別有利度が高止まりして差が出ない（`3d3131e` で修正済み）。
② 展開恩恵馬のピックアップに加えて絶対能力も加味した順位予想が欲しい → ユーザー判断で保留
（`tasks/backlog.md` B節、能力指数の算出方法自体の模索が必要なため）。

保留②を受け「他に実施すべき改善」の相談から**推奨1: データ取り込みの監視・鮮度表示**を実装（`2b83d75`）。
続けて「次の推奨する選択肢」として `tasks/backlog.md` C節の技術的負債に順に着手し、
(a) mypy --strict 全体エラーが誤情報だったと判明・訂正（`9ed1ff7`）、
(b) 旧handoffファイルの整理（`f2a8ea6`）、
(c) JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化（`24731ed`）を行った。

その後ユーザーから新規の不具合報告が2件続いた。
1件目: 「月曜なのに土日の開催結果と来週の特別登録馬が反映されていない」。調査の結果、
自動同期スクリプトが`--step special-entries`を一度も呼んでいなかったバグを発見・修正
（`c49ce05`）。土日結果側は別原因の可能性が高く、このクラウド環境からは診断できないため
ユーザーへ確認依頼中。
2件目: スクリーンショット2枚で「①一部のレース結果（9R〜11R）が反映されていない」
「②枠順確定前のレースなのに馬番が出ている」を報告。②はコードで原因を特定・修正
（`e2f0b3c`）。①はアプリ層のバグではなく取り込みギャップの可能性が高いと判断したが、
このクラウド環境からは特定できずユーザーへ確認依頼中、として一旦終了。

その後、ユーザーがWindows実行機で①の指示どおり手動再同期を実施した結果、状況がより
深刻かつ明確になっていたと判明: 実際は「9R〜11Rだけ」ではなく**2026-07-12以降（7/12・
7/18・7/19の全開催日）確定成績が一切反映されていない**一方、**7/25・26の特別登録は
正常に反映されている**とのユーザー報告。「取り込みは動いているが確定成績の検出だけが
機能していない」という手がかりから`mykeibadb_client._build_se_record()`のDATA_KUBUN
列の扱いに仮説を立て修正した（`af922a5`）。

**しかしユーザーが再pull＆再同期しても改善せず、DATA_KUBUN仮説は空振り**と判明。
同期ログは全ステップ exit code 0（＝件数ではなく「クラッシュしていない」だけ）で、
原因層すら特定できない状態だった。そこで方針を「推測で直す」から「測って切り分ける」へ
転換し、(1)`batch.py`に件数ログを常設、(2)切り分け診断ツール`ingestion.diagnose_results`を
新設、(3)`DaysBack`既定を7→10に修正した（下記「完了した作業」2.）。
その後の診断で解析は正常と判明し、送信段階の可視化で**解決に至った**（→「完了した作業」2.）。

---

## 完了した作業（直近セッション）

0H. **成績未取込警告から安全な手動再同期コマンドを提示**（本セッション）
   - domain/infrastructure: `RaceCompletenessRepository`へ最古未取込日取得を追加し、SQLの`min()`で
     全件をロードせず集計する。代表20件の範囲外も再同期対象に含められる。
   - application/API: 標準10日と最古未取込日までの日数の大きい方を
     `recommended_sync_days_back`として返す。OpenAPI/api-client型を再生成した。
   - Web: 警告・失敗・鮮度低下時だけ、リポジトリ直下から実行するPowerShellコマンドを提示。
     コピー成功・失敗をアイコン状態で伝える。正常時は表示しない。
   - 安全性: APIからWindowsプロセスは起動しない。直接起動は認証・ジョブキュー・多重実行防止が
     整うまで不採用とした。
   - テスト: API非統合464 passed、関連12 passed、Repository統合1 passed、Web67 passed、
     ruff、変更対象mypy、api-client/Web typecheck、Web build成功。

0G. **展開コメント生成をゼロコスト既定モードへ変更**（本セッション）
   - config: `COMMENT_GENERATOR_MODE`を`rule | gemini`のLiteral設定として追加。既定は`rule`で、
     未知の値はPydantic設定読込時に拒否する。
   - DI: APIキーの有無だけではGeminiを選ばず、`gemini`モードとキーが両方ある場合だけ
     `GeminiCommentGenerator`を生成する。キー欠損・初期化失敗はルールベースへ縮退する。
   - テスト: API非統合463 passed、関連29 passed、ruff、変更対象mypy strict成功。
     全体mypyは既知のNumPy型定義/Python設定不整合、import-linterは未導入のため未達。
   - 未確認・既知の不具合: なし。外部APIは意図的に呼び出していない。

0F. **Gemini既定モデルを3.5 Flashへ移行し、環境変数化**（本セッション）
   - config: `Settings.gemini_model`を追加。既定は`gemini-3.5-flash`、環境変数
     `GEMINI_MODEL`で上書き可能。`.env.example`にも設定例を追加した。
   - infrastructure/DI: `GeminiCommentGenerator`へ設定値を渡し、`reasons`には実際に
     使用したモデル名を記録する。Gemini版の世代を`comment-gemini-v3`へ更新した。
   - フォールバック: `GEMINI_API_KEY`未設定・呼出失敗時は従来どおり`comment-v2`を使用する。
   - テスト: API非統合457 passed、関連23 passed、ruff、変更対象3ファイルのmypy strict成功。
   - 未確認: 実API呼び出しはAPIキーと外部費用を使わないため未実施。HTTP経路はモックで検証済み。

0E. **枠順未確定時の展開コメント馬番号表示を修正**（本セッション）
   - domain: `horse_number_label.py`を追加し、確定時「N番」・未確定時
     「登録順 N（馬番未確定）」を共通化。scenario・commentaryの自然文へ適用。
   - application: `predict_formation()`の成否を枠順確定の単一判定とし、scenarioと
     `ForecastCommentInput.horse_numbers_confirmed`へ渡す。
   - infrastructure: Geminiプロンプト内の展開恩恵馬も同じ表示へ統一。
   - version: `comment-v2` / `comment-gemini-v2`。API公開スキーマ変更なし。
   - テスト: API非統合454 passed、関連74 passed、ruff、変更対象mypy strict成功。
   - 既知の不具合: なし。import-linter未導入と全体mypyのNumPy型定義問題は環境起因。

0D. **LightGBM Windows改行破損修正・AbilityWeights実DB採用判断**（本セッション）
   - `.gitattributes`: `apps/api/models/*.txt text eol=lf`を追加。Git blobとWindows作業ファイルの
     サイズ差（芝398,640→400,397 bytes）からCRLF変換による`tree_sizes`破損を特定した。
   - `lgbm_forecaster.py`: 読込前にCRLFをLFへ自己修復し、既存cloneも再checkout不要で救済。
     split/unifiedモデルの読込失敗を黙殺せず、フォールバック先と例外を警告する。
   - `TestCommittedModels`: 追跡中の芝・ダートモデルを実ロードし、両コースを予測する回帰テスト。
   - 実DB比較: 2025-07-01〜12-31を212レース、2026-01-01〜07-21を97レースで評価。
     全3指標が両期間で改善する候補はなく、`DEFAULT_WEIGHTS`は変更しないと決定。
   - 仮実装・未確定仕様: なし。成分重み以外の減衰・正規化定数は引き続き未確定。
   - 既知の不具合: なし。mypyのみローカルNumPy型定義とPython 3.11設定の不整合で、
     対象コードの型解析前に停止する。
   - テスト: API非統合449 passed、LightGBM関連31 passed、ruff、実DBバックテストCLI成功。

0C. **取り込み監視をデータ完全性へ拡張**（本セッション・OpenAI Codex）
   - domain: `RaceCompletenessRepository`を追加。既存の汎用`RaceRepository`は変更せず、
     状態監視に必要な読み取りだけを分離した。
   - infrastructure: `SqlAlchemyRaceRepository.count_incomplete_past_races()` /
     `find_incomplete_past_races()`を追加。日本時間の当日より前かつ`RaceStatus.ENTRIES`を対象に、
     件数と新しい順の代表20件をDBで取得する。
   - API: `IngestStatusOutput` / `IngestStatusSchema`へ`has_incomplete_races`、
     `incomplete_race_count`、`incomplete_races`を追加し、OpenAPIとapi-client型を再生成。
   - Web: `ingestStatusMeta()`で直近失敗を最優先、次に成績未取込、次に鮮度低下を表示。
     `IngestStatusBanner`の開閉領域から対象レースの予想画面へ移動できる。
   - 仮実装・暫定値: 詳細上限20件。当日開催分は正常な結果待ちとして除外。障害競走等の
     個別除外は未実装で、誤警告が確認された場合のみ見直す。
   - 既知の不具合: なし。Dockerを使うSQL実装用の`TestFindIncompletePastRaces`は実行済み。
     その他のintegration 18件は今回の対象外として未実行。
   - テスト: API非統合447 passed、関連SQL integration 1 passed、Web66 passed、ruff、
     Web typecheck/build成功。mypyのみローカルNumPy型定義とPython 3.11設定の不整合で停止。

0B. **AbilityWeightsの同一期間比較CLI**（本セッション・OpenAI Codex）
   - `DEFAULT_ABILITY_WEIGHT_PROFILES`に現行・近走のみ・近走重視・市場支持重視を定義。
   - `compare_ability_weight_reports()`で現行差を計算し、`format_ability_weight_comparison()`と
     `ability_weight_comparisons_to_dict()`でCLI/JSONへ出力。
   - `scripts/backtest_forecast.py --compare-ability-weights`を追加。現行レポートは再利用し、
     残り3候補だけを追加実行する。候補は自動採用しない。
   - API unit+contract 444 passed（関連は40 passed）、変更対象Ruff、mypy strict 58ファイル、
     CLI `--help`成功。実DBでの実行は未実施。

0A. **統合順位予想 Phase 2完成（grade・確定馬体重・検証指標）**（本セッション・OpenAI Codex）
   - ingestion: RA `GradeCD[615]`を公式コードから名称化。mykeibadb合成RAにも同位置へ書き込み。
     SE確定レコードの`BaTaijyu[324:327]`をresults送信へ追加し、gradeとともにAPIへ渡す。
   - API: `ResultBody.grade` / `ResultItem.body_weight`を追加。結果登録時に`races.grade`と既存
     `race_entries.weight`を更新。新規migrationは不要。
   - ability-v3: gradeをクラス係数へ優先利用し、欠損時のみrace_classへ縮退。馬体重は能力加点しない。
   - backtest: 統合順位の1位馬勝率・1位馬好走率・TOP3好走捕捉率をテキスト/JSONへ追加。
     `ForecastBacktester`へ`AbilityScorer`注入点を追加し、候補重みを同一期間で比較可能にした。
   - 検証: API unit+contract 440 passed、ingestion 191 passed、Web 65 passed、変更対象Ruff、lint-imports、
     api-client/web typecheck、Web build成功。mypy strictは既知の`lgbm_forecaster.py:58 unused-ignore`のみ。

0. **統合順位予想: UI刷新（印→タグ）＋ Phase2（人気・本賞金→ability-v2）**（前セッション・`7997931`）
   - **UI（ユーザーFB「印よりタグが分かりやすい・順位を明確に」）**: `IntegratedRankingView` 刷新。
     ◎○▲△の印を廃止、総合順位（1位…）を主役に、分類は言葉タグ（本命/対抗/穴（妙味）/人気でも注意/
     能力上位・中位/展開が向く・向きにくい）。プレゼン層のみ（`8cda3bb` のドメイン/スキーマは不変）。
   - **Phase2 データ永続化**: 人気(TANSHO_NINKIJUN)・獲得本賞金(KAKUTOKU_HONSHOKIN)を追加。経路=
     mykeibadb列 → SE合成の**予約offset**（jv_spec `Ninki`[541:543]/`Honsyokin`[543:552]・mykeibadb合成
     専用・未検証。jvlink実COMでは書かれず読み側で弾く）→ `parse_se_result`（妥当性ゲート）→ Ingest API
     （ResultItem/ResultInput）→ `RaceEntry`＋ORM＋repository＋**migration 003** → `race_entries.popularity/
     prize_money`。ingest_api の results payload にも追加。
   - **ability-v2**（`domain/pace/ability.py`）: form(近走着順×クラス)0.55＋本賞金(対数正規化)0.30＋
     人気0.15 を新しさ加重ブレンド。**データ無し成分は除外し重み再正規化 → 旧データは form のみ＝v1相当へ
     安全に縮退**（再取込まで壊れない）。本賞金が「入着時の稼ぎ＝相手クラス」を連続量で捉え、grade未永続化
     によるクラス係数 best-effort の限界を緩和。🧪重みは §9-16。
   - **運用（ユーザー作業・必須）**: `alembic upgrade head`（003）＋過去 results 再取込で人気/賞金が埋まる
     （`MANUAL_SYNC_GUIDE §7.5`）。未実施でも縮退動作で壊れない。
   - 検証: API 436 passed、ingestion 185 passed（+2 round-trip）、Web 65 passed・typecheck・build clean、
     ruff/lint-imports/mypy clean（既存 lgbm・ingestion tuple-concat debt のみ・新規0）。OpenAPI/schema.d.ts 再生成。

1. **統合順位予想（能力×展開）Phase1 を実装**（本セッション・`8cda3bb`）
   - 経緯: ユーザー要望「展開＋絶対能力の統合順位予想」（2026-07-12保留）を再開。独断で仕様化しない
     方針に従い、データ範囲と統合の見せ方をユーザーに選択提示 → **現データのみでPhase1** ＋
     **2軸分類（本命/対抗/穴/危険）** を採用（`docs/DECISIONS.md` 2026-07-21）。
   - domain（純粋・reasons・model_version付き）:
     - `pace/ability.py`（ability-v1）: 各近走 = 出走頭数正規化した着順 × クラス係数、を新しさ加重
       平均（直近5走）。0〜100の内部score。🧪仮係数は `AbilityWeights`。
     - `pace/integrated_ranking.py`（integrated-v1）: 能力のレース内相対順位（上位/中位/下位/評価難）
       × 展開適性(合致/中立/不利)で ◎本命/○対抗/△危険/▲穴/無印 に分類。表示順も2軸から決定的に導出
       （恣意的な重み合算は不採用＝ユーザー選択）。
   - 結線: `forecast_use_cases`（`_build_ability_score` で近走+過去レースからability構築→`build_
     integrated_ranking`）、`dto.py`（`IntegratedRankingOutput`/`IntegratedEntryOutput`）、
     `schemas.py`（同Schema）、OpenAPI再生成（`openapi.json`+`schema.d.ts`）、`api-client/src/index.ts`。
   - web: `IntegratedRankingView.tsx`（新規）を `RaceForecastDashboard` の隊列予想の前に配置。
     ◎○▲△・能力上位/中位・展開が向く/向きにくいを**言葉と記号**で表示（PCI/PAI等の実数値は非表示）。
   - 当時の既知の限界: `grade`未永続化で、クラス係数は`race_class`文字列のbest-effortだった。
     **この制約は本セッションのability-v3で解消済み**（上記0A）。
   - 検証: **apps/api はこの新コンテナで環境未構築だったため `python -m venv .venv && .venv/bin/pip
     install -e ".[dev]"` で構築**（下記「注意事項」）。API unit+contract 432 passed（+新規domain16・
     contract1）、Web 65 passed、api/web typecheck・build・ruff・lint-imports・mypy --strict すべてclean
     （既存の `lgbm_forecaster.py:58` unused-ignore 1件のみ＝当環境のlightgbm差異による既存・無関係）。

2. **【解決】確定成績が2026-07-12以降反映されなかった件**（本セッション）
   - 診断ツール`diagnose_results`で「**解析は正常（453件解析可・DATA_KUBUN='7'）**」と判明 → 原因は
     解析より下流と特定。`RecordRaceResultUseCase`はレース未登録で例外を投げるが、`batch.py`の
     `ingest_results`が**per-raceでcatchしてexit 0**にしていた（全送信失敗でも「成功・0件」に見える）。
   - 送信成功/失敗の件数ログ（「確定成績送信 …: 成功 X / 失敗 Y」・全滅時WARNING）を常設し可視化。
     ユーザーが最新コードで results ステップを各日付に再実行 → **全レース送信成功しアプリに反映（解決）**。
   - 恒久対策: 件数ログ・`diagnose_results`（RA突き合わせ含む）・`DaysBack`既定7→10。再発時は即切り分け可。
   - 残: 障害競走の成績が別途未反映（ユーザー保留）。第1仮説のDATA_KUBUN修正(`af922a5`)は空振りだが
     単調・無害のため残置。

3. **展開恩恵馬カードが枠順未確定の馬番を確定情報のように表示するバグを修正**（`e2f0b3c`）
   - ユーザー報告（スクリーンショット）: 枠順確定前のレースなのに「展開恩恵馬TOP5」等に馬番が出ている。
   - 原因: `formation-v1`（隊列予想）は`frame_no`で確定/未確定を判定し未確定時は`formation: null`に
     する設計だったが、同じ画面のPAI系出力`HorseFitOutput`にはそもそも`frame_no`が無く、
     この判定が一切されていなかった。特別登録段階の`horse_no`は`ingest_entries()`がUMABAN=0時に
     割り当てる暫定連番で、公式馬番ではない可能性がある。
   - 対応: `HorseFitOutput`/`HorseFitSchema`に`frame_no`を追加（`FormationHorseSchema`と異なり
     `ge=1,le=8`制約なし。0=未確定が正常値）。`forecast_use_cases.py`で`RaceEntry.frame_no`から
     供給。OpenAPI再生成。web側`lib/pace.ts`に`horseNumberLabel()`を新設し、`frame_no>0`なら
     「馬番 N」、`frame_no=0`なら「登録順 N（馬番未確定）」を返す。`RaceForecastDashboard.tsx`
     （TOP5カード・評価下げカード・先導候補チップ）・`HorseFitTable.tsx`・`app/page.tsx`
     （トップ画面の中心候補プレビュー）の計5箇所を統一。
   - PAIスコア自体は枠順確定前でも意味があるため、formation-v1のように出力ごと非表示にはせず、
     ラベルの誠実さだけを是正する方針とした（`docs/DECISIONS.md`参照）。
   - **後続対応**: `scenario.py`を含む自然文コメントの同種問題は2026-07-22の
     `comment-v2`で解決済み。
   - 検証: API 415 passed（+1）、Web 65 passed（+2）、ruff/mypy --strict/lint-imports/
     typecheck/build すべてclean。

4. **自動同期が来週の特別登録を一度も取り込んでいなかったバグを修正**（`c49ce05`）
   - ユーザー報告「月曜なのに土日の結果・来週の特別登録馬が未反映」を調査。
     `run_mykeibadb_full_sync.ps1`（Task Scheduler「PCI_Sync_Mykeibadb」金/土10:00・日18:00が実行）は
     `batch.py --step entries`/`--step results` のみを呼んでおり、`--step special-entries`
     （mykeibadbの`TOKUBETSU_TOROKUBA`系という**別テーブル**を読む独立ステップ）を一度も
     呼んでいなかったと判明。`setup_task_scheduler.ps1`自身のdocstringは「日曜18:00は来週の
     重賞特別登録取り込みも兼ねる」と明記しており、実装漏れと判断（`docs/DECISIONS.md`参照）。
   - 対応: `run_mykeibadb_full_sync.ps1`に3番目の呼び出し（同じ過去7日〜未来14日の日付窓で
     `-Step special-entries`）を追加。`sync_mykeibadb.bat`・`MANUAL_SYNC_GUIDE.md`（手順・
     注意書き・6.8節トラブルシューティング新設）・`docs/SPEC.md §6`・`docs/DECISIONS.md`を更新。
   - `--step special-entries`自体はbatch.py/mykeibadb_client.pyで既に実装・単体テスト済みの
     機能で、`run_batch.ps1`のリトライ/Webhook通知も汎用対応済みだったため、追加は自動実行
     スクリプトへの呼び出し1行の低リスクな変更。
   - **未解決**: 「土日の確定成績が反映されていない」側は自動実行の対象内（`--step results`）
     のはずで、「取りこぼし」ではなく「実行自体の失敗/未発火」の可能性が高いが、Task Scheduler
     実行履歴・ログ・MySQL80サービス状態はこのクラウド環境から確認できないため、ユーザー自身の
     診断が必要（`MANUAL_SYNC_GUIDE.md §6.8`に診断手順を用意、ユーザーへ確認依頼中）。
   - コード修正のみでは今週分の取りこぼしは遡って埋まらないため、`--step special-entries`の
     手動実行コマンドを別途ユーザーへ案内。

5. **JV-Dataバイトオフセットの JV-Link新バージョン追従手順の明文化**（`24731ed`）
   - `tasks/backlog.md` C節に着手。`apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` を新規作成し、
     `dump_records.py`→`verify_layout.py`（アンカー検証→フィールド目視確認）→`locate_haron.py`/
     `locate_corners.py`（新オフセット特定）→`jv_spec.py`更新→テスト更新→記録、という一連の手順と
     安全策（1レースだけでCONFIRMED昇格しない等）を明文化。
   - 調査で判明: UM/KS/CH（`master_parsers.py`）は Ver.3.0.0→Ver.4.9 の実データ差分
     （ketto_num直後に日付フィールド群24byte追加、名前位置シフト）を既に確認・反映済みという実例が
     存在した。一方RA/SE（`jv_spec.py`）はREADME.md/common.pyが「Ver.3.0準拠」と書いたままで、
     実際にどのバージョンの出力を元に校正したかは未確認（独断で確定せず`docs/SPEC.md §9`-8に記録）。
   - `README.md`・`docs/SPEC.md`（§6, §9-8）から新ガイドへの相互参照を追加。コード変更なし。
   - 未完了: 実際の再検証実施はWindows実行機（JV-Link必須）が必要なため、このセッションでは
     手順の明文化のみ。実施自体は引き続き未着手。

6. **旧handoffファイルの整理**（`f2a8ea6`）
   - `docs/handoff-claude-code-2026-06-25.md` を精査。全項目が (a) 現構成と食い違う誤情報
     （`domain/services.py`・`infrastructure/repositories.py`は現存しない旧パス、
     「次に推奨する作業」は全項目完了済み）か、(b) 既存資料で完全に上書き済み
     （ローカル起動→`apps/api|web/README.md`、mykeibadb `.env`→`.env.example`、
     同期手順→`MANUAL_SYNC_GUIDE.md`、ディレクトリ構成→`docs/ARCHITECTURE.md`）と判明。
     「吸収すべき未収録の情報」が残っていなかったため削除（Git履歴には残り復元可能）。
   - 他ドキュメントからの参照は `tasks/backlog.md` のみだったことを確認済み（削除後に更新）。

7. **mypy --strict 全体エラーは誤情報だったと判明・訂正**（`9ed1ff7`、コード変更なし）
   - `tasks/backlog.md` C節「mypy src/ --strict を全体で通すためのスタブ導入」に着手する過程で、
     `python -m mypy src/ --strict` を実行したところ **56ファイル全体で0エラー**（キャッシュ削除後も再現）。
   - 原因: 素の `mypy` コマンドが `/root/.local/bin/mypy`（`uv tool` 等で別途インストールされた、
     プロジェクトの依存関係が入っていない隔離環境）を指しており、fastapi/sqlalchemy/pydantic
     （実際はいずれも py.typed 同梱で型情報あり）を「見つからない」という誤エラーを出していた。
     `pytest`と全く同じ根本原因（前セッションで発見済みの問題と同型）。
   - 対応: `CLAUDE.md`, `AGENTS.md`, `docs/PROJECT_RULES.md`, `docs/ARCHITECTURE.md`,
     `apps/api/README.md`, `tasks/backlog.md` の「環境要因・コード欠陥ではない」という誤記載を
     すべて訂正し、`python -m mypy src/ --strict`（全体0エラー）を正しい実行方法として明記。
   - Definition of Done も「domain・applicationは0エラー」から「全体で0エラー」へ引き上げ
     （実態がその基準を既に満たしていたため）。
   - 検証: `rm -rf .mypy_cache && python -m mypy src/ --strict` → Success: no issues found in 56 source files。

8. **データ取り込みの鮮度監視**（`2b83d75`）
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
     届くかの実地確認。再同期コマンド提示は0Hで実装済み。APIからの直接起動は安全要件未整備のため不採用。

9. **脚質別有利度の修正（style-advantage-v1）**（`3d3131e`）
   - 原因: web が「その脚質の最大PAI」を有利度に流用しており、スコアが60〜96に高止まり。
   - 対応: `domain/pace/style_advantage.py` 新設。想定RPCIの中立点（classify_pace と同じ
     rule-v4 閾値の中点: 芝50/ダート43）からの乖離を 50=互角の対称スコア（0〜100）へ写像。
     逃げ・追込は増幅1.2、逃げ候補2頭以上で逃げのみ競合減点。reasons/model_version 付き。
   - `StyleAdvantageWeights` は🧪仮係数（`docs/SPEC.md §3.4/§9`-11、`docs/DECISIONS.md` 2026-07-12）。

9a. **脚質別展開有利度の実DB検証基盤**（`66568ad`）
   - `ForecastBacktester`へ有利群・不利群の好走率、リフト、好走率差、point-biserial相関とJSON明細を追加。
   - `backtest_forecast.py --validate-style-advantage`は確定RPCI・確定脚質を使い、係数の方向性だけを
     高速診断する。`--output`で診断サマリをJSON保存できる。本番予測精度として扱わない。
   - 実DB診断（各1000レース）: 芝7952頭で有利26.4%／不利19.3%（差+7.1pt）、
     ダート8618頭で33.0%／14.0%（差+19.0pt）。ルール方向は妥当。
   - 予測込み（各100レース）: 芝17.6%／27.8%（差-10.2pt）、ダート28.5%／19.7%（差+8.8pt）。
     芝だけ逆転するため`StyleAdvantageWeights`は変更せず、想定RPCIと脚質予測の切り分けを残した。

9b. **脚質別展開有利度の誤差要因診断**（本セッション）
   - `ForecastBacktester.diagnose_style_advantage()`と`--diagnose-style-advantage`を追加。
   - 4パターンで共通して脚質を判定できた馬だけを使い、母集団差による誤読を防ぐ。
   - `--venue-code`で開催場別診断、`--output`でJSON保存が可能。前セッションで混入した
     `args.output.write_text`（`str`に対する誤呼び出し）も通常のJSON writerへ修正。
   - 実測値は`docs/SPEC.md §3.4`と`docs/DECISIONS.md` 2026-07-23を参照。

10. **バックテスト結果のJSON保存**（`03bc005`）
   - `report_to_dict()` + `--output <path>`。混合＋track別内訳をJSON保存。print出力は不変。

11. **Codex引き継ぎ内容の検証**（`af66e8f`、ドキュメントのみ）
   - ローカルが`origin`より7コミット遅れていたため`git merge --ff-only`で追従（無傷）。
   - Codexの実装3件をコードレベルで検証し、テストを独立再実行。重大な不整合なし。

12. **混在型脚質の距離対応予測**（`2b083ba`、Codex実装・検証済み）
   - 直近20レース266頭を調査し、旧自在139頭のうち99頭が60%未満の混在、40頭が履歴なしと確認。
   - 明確な `running-style-v1` 判定は維持し、混在型だけ `running-style-v2-distance` で再判定。
   - 過去5走の4角位置、対象距離との距離差、近走順を使用。先行・差し同数時の距離規則を追加。
   - 予想日以後の成績を参照しないよう、履歴取得に開催日前カットオフを明示。
   - 同じ266頭で自在を139頭（52.3%）から40頭（15.0%）へ削減。履歴なしは参考のまま維持。
   - API 380件、Web 55件、ruff/mypy/import-linter/typecheck/buildがすべて成功。

13. **枠順確定後の隊列予想**（`c679e09`、Codex実装・検証済み）
   - `domain/pace/formation.py` に枠順確定判定と formation-v1 を追加。
   - 全馬の枠番が1〜8、馬番が正かつ一意の場合のみ予想し、特別登録（frame_no=0）は `null`。
   - 脚質70%・近走の1角（欠損時4角）位置30%で先頭/好位/中団/後方へ配置。
   - 各馬に日本語の根拠と「高・標準・参考」の信頼度ラベルを付与。
   - OpenAPI/API Clientを再生成し、WebにJRA枠色の `FormationView` を追加。
   - 契約テストの予測器をルールベースへ固定し、WindowsのLightGBMネイティブabortを回避。
   - 実DBで entries 278件、枠順確定112件は生成、未確定166件は非生成を確認。

14. **レース分析UIの刷新**（`4d9e5b5`、Codex実装・検証済み）
   - `AppHeader` を追加し、全画面でブランドとレース一覧への導線を固定。
   - レース一覧を最大幅拡張し、統計、開催日カレンダー、日付・競馬場別レースを2カラム化。
   - 展開予想と確定後回顧へ共通のダークヒーローとエメラルドのアクセントを導入。
   - 予想サマリー、初心者向け解説、展開恩恵馬、評価を下げたい馬の視覚階層を整理。
   - 回顧画面は「PCI判定」を「ペース傾向」へ翻訳し、内部実数値を新たに露出していない。
   - モバイルでは1カラム、デスクトップでは一覧のカレンダーをstickyサイドバーとして表示。

以下は以前の完了作業:

15. **`backtest_forecast.py` の track別内訳を既定表示に追加**（`d840e66`）
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
16. **想定RPCI 受入基準の未達方針を決定**（`docs/DECISIONS.md` 2026-07-11、`d840e66`）
   - 判断: 現行モデル（lgbm-turf-v1/lgbm-dirt-v1）のまま運用継続。MAE≤1.5 を追う追加投資は今は行わない。
   - 詳細な理由・不採用案・見直し条件は `docs/DECISIONS.md` の該当エントリを参照。
17. **想定RPCI 精度の検証**（`c94f708`、コード変更なし）
   - ユーザーが実DB（mykeibadb蓄積データ）で `python -m scripts.backtest_forecast --limit 200` を
     3パターン（混合／芝／ダート）実行、結果を `docs/SPEC.md §8/§9` と `docs/adr/0005 §5.4` に記録。
   - 結果概要: MAE≤1.5 は構造的に未達（混合7.848/芝8.861/ダート8.332）。ラベル一致率≥60% は
     芝(73.5%)・混合(61.0%)は達成、ダート(42.5%)は未達。混合サンプルだと PAI point-biserial が
     希釈されて見える（+0.009）が track別だと正の相関（芝+0.084/ダート+0.032）に戻る新知見あり。
18. **`forecast_accuracy` の UI 表示**（`e65f919`）、**AI 引き継ぎ基盤整備**（`004aead`）、
    **予測フィードバックループ**（`9712fd2`）ほか、それ以前の完了作業は
    `tasks/current.md`「最近完了したタスク」参照。

## 未完了の作業

- **確定成績未反映は解決済み**（上記「完了した作業」2.）。残る関連事項は障害競走の成績が別途
  未反映（ユーザー保留）のみ。
- **統合順位予想 Phase2・AbilityWeights比較CLI・実DB採用判断は完了**。残る検証は、
  実JV-Link COMにおけるGradeCD[615]および人気/賞金予約オフセットの確認（`tasks/backlog.md` B節）。
- **脚質別展開有利度の複数年・距離・馬場状態別比較は完了**。7月小倉芝1200mだけ
  `reference`表示とし、`StyleAdvantageWeights`は未変更。福島の想定RPCI誤差は調査候補として残る。
- **Windows実行機での実地確認が必要な残課題**（このクラウド環境からは検証不可）:
  `NOTIFY_WEBHOOK_URL` のWebhook通知が実際に届くか。`special-entries`呼び出しを追加した
  自動同期スクリプト自体がWindows実行機で問題なく動くかも未確認。
- 画面からの安全な再同期コマンド提示は完了。直接実行ボタンは認証・ジョブキュー・多重実行防止が
  未整備のため意図的に実装していない。
- **JV-Data仕様追従の実施自体は未着手**（`apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md`で
  手順は明文化したが、実データ取得にはWindows実行機＋JV-Linkが必要でこのクラウド環境からは不可。
  RA/SEが実際にVer.3.0.0/Ver.4.9のどちらの出力を元に校正されたかも未確認のまま、`docs/SPEC.md §9`-8）。
- それ以外はなし。

## 現在止まっている箇所

**コード実装は停止していない。** 馬場情報バックフィルと再検証は完了した。
現在の最優先残件は、検出した重複450組の正規キー判定とFK移行設計である。

---

## 次に実施すべき作業（候補・優先順位順）

ユーザーからの新規指示がない場合、以下の優先順で `tasks/backlog.md` から着手を検討する。
**どれを選ぶかはユーザー確認を推奨**（`docs/PROJECT_RULES.md` の「独断で正式仕様化しない」方針）。

0. **P1 重複レース450組の安全な統合設計**。
   正規キー候補、関連FK件数、成績・頭数・出走馬差分をdry-runし、自動統合可能な組を分類する。
   dry-runとトランザクション設計が完成するまで削除処理は追加しない。
1. **P2 実JV-Dataの人気/賞金予約オフセット検証**。Windows実行機のJV-Link COMが必要。
   `JV_SPEC_MAINTENANCE_GUIDE.md`の手順に従い、実レコードの位置を確認してから正式化する。
2. **P2 暫定定数の検証と正式化**（`_NEIGHBOR_BLEED_RATIO`・`RuleWeights`・`PaiWeights`・
   `FormationWeights`・`DistanceStyleWeights`・`STALE_AFTER_DAYS`・
   `AbilityWeights`の成分重み以外）
   - 実データ・実運用での検証が前提のため、想定RPCI検証と同様「ユーザーが実DBでスクリプト実行/
     しばらく運用→結果を分析」の進め方になる可能性が高い。着手前にどの定数を対象にするか確認する。
3. **Webhook通知のWindows実地確認**。`NOTIFY_WEBHOOK_URL`を設定し、失敗時に通知が届くか確認する。

**保留・確認待ちの項目**:
- APIからの直接再実行ボタン化 — 認証・ジョブキュー・多重実行防止・Windows接続方式が整うまで保留。

**見直し条件つきで保留中の項目**（`docs/DECISIONS.md` 参照。トリガーが来るまでは着手しない）:
- ダート特徴量追加・学習データ拡張（2026-07-11決定） — `forecast_accuracy` 蓄積が増える、
  またはダートの外れに偏りが見えた場合に再検討。

---

## 変更対象ファイル（直近セッション）

馬場状態欠損のデータ完全性監視と復旧導線:
- API: `application/dto.py`, `application/ingest_status_use_cases.py`,
  `domain/racing/repository.py`, `infrastructure/repositories/race_repository.py`,
  `presentation/schemas.py`
- Web: `apps/web/src/lib/ingestStatus.ts`, `apps/web/src/components/IngestStatusBanner.tsx`
- worker: `apps/ingestion-worker/scripts/run_batch.ps1`
- tests: API unit/contract/PostgreSQL integration、Web `ingestStatus.test.ts`
- generated: `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`
- docs/tasks: worker `README.md`、`docs/SPEC.md`、`docs/DECISIONS.md`、
  `docs/HANDOFF.md`、`tasks/current.md`、`tasks/backlog.md`

それ以前の直近セッション:

mykeibadb馬場状態・天候の取り込みとバックフィル:
- API: `application/race_use_cases.py`, `presentation/routers/ingest.py`
- worker: `models.py`, `client/base.py`, `client/mykeibadb_client.py`, `ingest_api.py`, `batch.py`
- tests: APIのrace use case/ingest契約、workerのmykeibadb/API/batch E2E

安全な手動再同期支援で変更したファイル:
- API: `domain/racing/repository.py`, `application/dto.py`, `application/ingest_status_use_cases.py`,
  `infrastructure/repositories/race_repository.py`, `presentation/schemas.py`
- Web: `apps/web/src/lib/ingestStatus.ts`, `apps/web/src/components/IngestStatusBanner.tsx`,
  `apps/web/src/components/IngestRecoveryCommand.tsx`
- 型: `packages/api-client/openapi.json`, `packages/api-client/src/schema.d.ts`
- テスト: API unit/contract/integrationの取り込み監視・Repositoryテスト、
  `apps/web/src/lib/ingestStatus.test.ts`
- 文書: `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`,
  `docs/DECISIONS.md`, `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

Geminiモデル移行で変更したファイル:
- API: `apps/api/src/pci/config/settings.py`,
  `apps/api/src/pci/infrastructure/llm_comment_generator.py`,
  `apps/api/src/pci/presentation/dependencies.py`, `apps/api/.env.example`
- テスト: `apps/api/tests/unit/test_settings.py`,
  `apps/api/tests/unit/infrastructure/test_llm_comment_generator.py`
- 文書: `apps/api/README.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`,
  `docs/DECISIONS.md`, `docs/adr/0008-commentary-generation-strategy.md`,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

ゼロコスト既定モードで変更したファイル:
- API: `apps/api/src/pci/config/settings.py`, `apps/api/src/pci/presentation/dependencies.py`,
  `apps/api/.env.example`, `apps/api/README.md`
- テスト: `apps/api/tests/unit/test_settings.py`,
  `apps/api/tests/unit/presentation/test_dependencies.py`
- 文書: `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `docs/DECISIONS.md`,
  `docs/adr/0008-commentary-generation-strategy.md`, `tasks/current.md`, `tasks/backlog.md`,
  `docs/HANDOFF.md`

`7997931`（Phase2＋UI刷新）で変更したファイル:
- ingestion: `models.py`（ResultRecord+人気/賞金）, `parser/jv_spec.py`（SE予約offset Ninki/Honsyokin）,
  `parser/se_parser.py`（読取+妥当性ゲート）, `client/mykeibadb_client.py`（列→合成書込）,
  `ingest_api.py`（payload）, `tests/test_mykeibadb_client.py`（round-trip +2）
- API: `presentation/routers/ingest.py`（ResultItem）, `application/dto.py`（ResultInput）,
  `application/race_use_cases.py`（RecordRaceResult 反映）, `domain/racing/race_entry.py`（フィールド）,
  `infrastructure/database/models.py`（ORM列）, `infrastructure/repositories/race_repository.py`（read/write）,
  `alembic/versions/003_add_entry_popularity_prize.py`（新規migration）,
  `domain/pace/ability.py`（ability-v2 ブレンド）, `tests/unit/domain/pace/test_ability.py`（+4）
- 型/web: `packages/api-client/openapi.json`+`src/schema.d.ts`（再生成）,
  `apps/web/src/components/IntegratedRankingView.tsx`（印→タグ・順位主役に全面刷新）
- ドキュメント: `docs/SPEC.md`（§3.6 ability-v2化・§9-16更新）, `docs/DECISIONS.md`（2026-07-21（2））,
  `apps/ingestion-worker/MANUAL_SYNC_GUIDE.md`（§7.5 migration+再取込手順）,
  `tasks/current.md`, `tasks/backlog.md`, `docs/HANDOFF.md`

`8cda3bb`（統合順位予想 Phase1: ability-v1/integrated-v1・domain+app+schema+web+contract）で変更:
  `e286d94`（送信失敗可視化+RA突き合わせ）, `ccd6dc2`（診断ツール）, `af922a5`（DATA_KUBUN・空振り）。

（展開恩恵馬frame_noガード追加はコミット `e2f0b3c`、自動同期special-entries修正は `c49ce05`、
JV-Data仕様追従ガイド新規作成は `24731ed`、旧handoffファイル削除は `f2a8ea6`、
mypy誤情報訂正の変更ファイル一覧はコミット `9ed1ff7`、データ取り込み鮮度監視は `2b83d75`、
style-advantage-v1 は `3d3131e`、Codex実装分 `2b083ba`/`c679e09`/`4d9e5b5` の変更ファイル
一覧は各コミットまたは `docs/DECISIONS.md`/`docs/SPEC.md` の該当エントリ参照）

---

## 未確定仕様

- ❓ 受入基準「ラベル一致率≥60%」を blended/track別のどちらで判定するかは未確定
  （`docs/SPEC.md §9`-3）。基準を定めた側（プロダクトオーナー）の確認が必要。
- ❓ PAI の正式定義・重み（pai-v2 も重みは暫定、`docs/SPEC.md §9`-1）。
- ❓ 脚質判定ルールの最適化基準、展開コメントのLLM本採用可否、本番認証・課金仕様
  （いずれも `docs/SPEC.md §9` にリストあり、詳細はそちらを参照）。
- ❓ Geminiの正式運用品質基準・費用上限・モデル更新時の受入手順。任意実装とフォールバックは
  完成しているが、無料枠・料金・提供モデルはGoogle側で変更され得る。
- 🔎 formation-v1 の脚質70%・近走序盤位置30%と4ゾーン境界は実データ評価前の仮仕様
  （`tasks/current.md` の「暫定定数の検証と正式化」に追跡タスクあり）。
- 🔎 `STALE_AFTER_DAYS=4`（取り込み鮮度監視の暫定閾値）が実運用（週3回同期）に対して
  適切かは、しばらく運用してから検証する（`docs/SPEC.md §9`-13）。
- 🔎 RA/SE（`jv_spec.py`）の実測校正済みバイトオフセットが JV-Data仕様書の Ver.3.0.0 と
  Ver.4.9 のどちらの出力を元にしたものかは未確認（`docs/SPEC.md §9`-8、本セッションで発見）。
  UM/KS/CH（`master_parsers.py`）は既に Ver.4.9 相当への移行を確認済みだが、RA/SEは
  README.md/common.pyが「Ver.3.0準拠」表記のまま。再検証手順は
  `apps/ingestion-worker/JV_SPEC_MAINTENANCE_GUIDE.md` に明文化済み（実施はWindows実行機が必要）。
- ✅ 展開コメント自然文の枠順未確定表示は`comment-v2`で解決済み。
- 🔎 **`mykeibadb_client._build_se_record()`のDATA_KUBUN修正（2026-07-20）は実DB未検証**
  （`docs/SPEC.md §9`-15、`docs/DECISIONS.md` 2026-07-20）。コードリーディングのみに基づく
  仮説的な修正で、ユーザーの再同期結果で検証されるまでは「原因はこれで確定」と扱わないこと。

## 仮実装

- 🧪 `RuleWeights`(rule-v4)・`PaiWeights`(pai-v2)・`_NEIGHBOR_BLEED_RATIO=0.4`・
  上がり3F 妥当範囲(25〜55秒)。いずれも独断で確定しないこと（`docs/SPEC.md §9`）。
- 🧪 `FormationWeights`（脚質0.7・近走序盤位置0.3）。`formation-v1` として隔離済み。
- 🧪 `DistanceStyleWeights`（近走減衰・距離差・先行距離補正）。
  `running-style-v2-distance` として隔離済みで、隊列ゾーン一致率による再検証が必要。
- 🧪 `StyleAdvantageWeights`（勾配4.0/pt・逃げ追込増幅1.2・逃げ競合減点6.0/頭）。
  `style-advantage-v3`として隔離済み。7月小倉芝1200mの`reference`条件は馬場状態バックフィル後に見直す。
- 🧪 `STALE_AFTER_DAYS=4`（取り込み鮮度監視、`domain/ops/ingest_log.py`。本セッション追加）。
- 🧪 想定RPCI 受入基準の未達に対する運用方針は暫定決定（追加投資しない、`docs/DECISIONS.md`）。
  見直し条件に該当したら再検討する前提。

## 既知の不具合

- **未確認（Gemini）**: 実APIキーを用いた疎通は未実施。単体テストではHTTP成功・失敗・
  モデル上書き・ルールフォールバックをモック検証済み。ローカルで疎通する場合は費用条件を
  公式料金表で確認してから`COMMENT_GENERATOR_MODE=gemini`と`GEMINI_API_KEY`を設定する。
- **解決済み**: 確定成績が2026-07-12以降反映されなかった件（上記「完了した作業」2.）。診断で
  解析は正常と判明、`batch.py`が`record_results`失敗をexit 0に握りつぶしていた欠陥を可視化。
  ユーザーが最新コードで再実行→全レース送信成功しアプリに反映。
- **未解決（ユーザー保留）**: 障害競走の成績が別途未反映。今回の一連とは切り分けて保留中。
- **残置（空振り・無害）**: `_build_se_record()`のDATA_KUBUN修正（`af922a5`）。真因ではなかったが
  単調・無害のため残置。
- **修正済み**: 展開恩恵馬カード等が枠順未確定の馬番を確定情報のように表示していた
  （`e2f0b3c`、上記「完了した作業」3.）。
- **修正済み**: 自動同期スクリプトが`--step special-entries`を一度も呼んでいなかった
  （`c49ce05`、上記「完了した作業」4.）。

---

## テスト状況（2026-07-21・統合順位予想 Phase 2完成後）

### OpenAI Codex による Phase 2完成後の全量確認

| 対象 | コマンド | 結果 |
|---|---|---|
| API 単体+契約 | `PYTHONPATH=src python -m pytest tests/unit tests/contract -q` | **440 passed** |
| ingestion-worker | `PYTHONPATH=src python -m pytest tests -q` | **191 passed** |
| API変更対象Ruff | `python -m ruff check <変更ファイル>` | **成功** |
| ingestion変更対象Ruff | `python -m ruff check <変更ファイル>` | **成功** |
| API import境界 | `lint-imports` | **2 kept, 0 broken** |
| API型 | `python -m mypy src --strict --python-version 3.12` | 既存`lgbm_forecaster.py:58` unused-ignore 1件のみ |
| api-client型 | `npm.cmd run typecheck --workspace=@pci/api-client` | **成功** |
| Web単体 / 型 / build | `npm.cmd run test` / `typecheck` / `build` | **65 passed** / **成功** / **成功** |
| OpenAPI | `PYTHONPATH=src python scripts/export_openapi.py` + api-client generate | **再生成済み** |

注意: WindowsのグローバルPythonには別チェックアウト`C:\Users\yuuta\PCI_app`がeditable installされている。
検証時は必ず現在の作業ツリーで`PYTHONPATH=src`を明示すること。実DBバックテストとJV-Link COM実地確認は未実行。

### OpenAI Codex によるマージ後再確認（2026-07-21）

`origin/claude/sweet-einstein-ilnaov` の16コミットを取り込むマージ中に、競合解消後の状態で以下を再実行した。
このCodex環境では `python`/`py`/`ruff`/`mypy`/`lint-imports` がプロジェクトvenvとして使える状態ではなく、
API/ingestion-worker の全量pytest・ruff・mypyは再実行できなかった。Claude Code 側の全量結果は下表に残す。

| 対象 | コマンド | 結果 |
|---|---|---|
| 競合マーカー確認 | `rg -n "<<<<<<<|=======|>>>>>>>"` | **該当なし** |
| API 構文確認 | `python.exe -m py_compile src\pci\application\backtest.py scripts\backtest_forecast.py tests\unit\application\test_backtest.py`（Codex bundled Python） | **成功** |
| api-client 型 | `npm.cmd run typecheck --workspace=@pci/api-client` | **成功** |
| Web 型 | `npm.cmd run typecheck`（apps/web） | **成功** |
| Web 単体 | `npm.cmd run test`（apps/web） | **65 passed** |
| Web build | `npm.cmd run build`（apps/web） | **成功** |

補足: Codexローカルの `144ebfd` は同目的のJSON保存を先に実装していたが、リモート `03bc005` の
`report_to_dict`/`--output` 実装が既に存在したため、競合ファイルはリモート版を採用した。

| 対象 | コマンド | 結果 |
|---|---|---|
| **API 単体+契約** | `.venv/bin/python -m pytest tests/unit/ tests/contract/ -q`（要 venv・下記注意事項） | **436 passed** |
| API Lint | `.venv/bin/ruff check src/ tests/ scripts/` | 既存 `scripts/seed_dev.py` 10件のみ（未編集ファイル・無関係。新規0） |
| API import境界 | `.venv/bin/lint-imports` | **2 kept, 0 broken** |
| API 型（全体） | `.venv/bin/python -m mypy src/ --strict` | 既存 `lgbm_forecaster.py:58` unused-ignore 1件のみ（当環境のlightgbm差異・無関係。新規0） |
| OpenAPI同期 | `test_committed_openapi_is_in_sync` | **成功**（`export_openapi.py`で再生成済み） |
| api-client 型 | `npm run typecheck`（packages/api-client） | **成功** |
| Web 単体 / 型 / build | `npm run test` / `typecheck` / `build`（apps/web） | **65 passed** / **成功** / **成功** |
| **ingestion-worker 単体** | `.venv/bin/python -m pytest tests/ -q`（要 3.12 venv） | **185 passed** |
| ingestion-worker Lint | `.venv/bin/ruff check src/ tests/` | 既存18件のみ（`windows_client.py`/`locate_corners.py`/`test_batch_e2e.py`等・未編集ファイル。新規0） |
| ingestion-worker 型 | `.venv/bin/python -m mypy src/ --strict` | 既存25件のみ（pymysqlスタブ欠如・`mykeibadb_client.py`のtuple-concatパターン・`batch.py`の`ingest_masters`。新規0） |

未実行: integration（Docker/testcontainers前提）。実DB依存の検証はこのクラウド環境から不可。

---

## 注意事項

- **新コンテナでは apps/api も依存未インストール。** 素の `python` に pytest/fastapi 等が無く、
  `pytest`/`mypy` は `uv tool` の隔離環境（プロジェクト依存なし）を指すことがある。
  **apps/api でも venv を作ること**: `cd apps/api && python -m venv .venv && .venv/bin/pip install -e ".[dev]"`、
  以降 `.venv/bin/python -m pytest` / `.venv/bin/python -m mypy src/ --strict` / `.venv/bin/ruff` /
  `.venv/bin/lint-imports` を使う（`.venv` は gitignore 済み）。ingestion-worker は 3.12 venv（別項）。
  **2026-07-12判明**: 「mypy全体でスタブ未導入エラー多数」は誤りで、venv経由なら実質0エラー
  （当環境で残る `lgbm_forecaster.py:58` unused-ignore 1件は lightgbm のバージョン差由来で無害）。
- このクラウド実行環境からは本番相当DB（mykeibadb蓄積データ）に**接続できない**。
  実データに依存する検証（バックテスト・実運用での鮮度判定・Webhook到達確認等）は
  ユーザーに手元（Windows機）で実行してもらい、出力を貼ってもらって分析する進め方になる。
- `backtest_forecast.py` の track別内訳表示は予測を2回実行するため、`--limit` を大きくすると
  実行時間が伸びる（上記「完了した作業」14.の既知のトレードオフ参照）。
- UI（Next.js）には PCI/RPCI/PAI の実数値を出さない方針（`docs/PROJECT_RULES.md §5`）。
  ただし CLI診断ツール（`backtest_forecast.py`等）は開発者向けであり、この方針の対象外
  （実数値をprintするのは意図的な挙動）。取り込み鮮度監視の失敗詳細（エラー要約）も、
  対象がPCI/RPCI等の指標ではなく運用ログのため同ルールの対象外（運用者本人向け情報）。
- `batch.py --mode mykeibadb` の `entries`/`results` と `special-entries` は**別のmykeibadbテーブル**
  （前者はRA/SE、後者はTOKUBETSU_TOROKUBA系）を読む独立ステップ。`--step all` は
  masters/entries/resultsのみで special-entries は含まれない。「取り込みが動いている」ことと
  「特別登録も含めて動いている」ことは別。今後この領域を触る際は両方を意識すること
  （2026-07-13、自動同期スクリプトの呼び出し漏れとして発見）。
- **`frame_no`（枠番）は`horse_no`（馬番）と別概念で、確定タイミングも異なる**。特別登録段階
  （枠順確定前）では`frame_no=0`かつ`horse_no`が`ingest_entries()`の暫定連番の場合がある。
  新しく馬単位の出力を追加する際は、`frame_no`（0=未確定/1〜8=確定）で判定してから`horse_no`を
  「確定馬番」として扱うこと。既存の判定基準は`formation.has_confirmed_draw()`
  （レース全体で1つの判定）と`lib/pace.ts`の`horseNumberLabel()`（表示ラベル）の2箇所
  （2026-07-13、`HorseFitOutput`の表示バグ修正で追加）。
- **`apps/ingestion-worker`はPython 3.12専用**（`pyproject.toml`の`requires-python`）。
  このクラウド環境の既定Pythonは3.11で、かつ最初はpytest等が一切インストールされていない
  （apps/apiと違い事前セットアップ済みの環境ではない）。テストを実行する際は
  `cd apps/ingestion-worker && python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`
  で環境を作り、`.venv/bin/python -m pytest tests/`を使うこと（2026-07-20判明）。
- **mykeibadbの列マッピング関連の不具合は「無いのではなく、値の意味が合わない」形で起きやすい**。
  過去に列名不一致で確定成績が全件消えた回帰
  （`test_iter_se_records_parses_results_from_wmykeibadb_columns`）があり、今回のDATA_KUBUN
  修正もその変種（列は存在するが値の意味づけが期待と異なる）。mykeibadb連携で「取り込みは
  成功するのにデータが空/古いまま」という報告を受けたら、まずこの種の暗黙の前提のズレを疑う
  こと（2026-07-20）。

---

## 次の担当者が最初に読むべきファイル（順番）

1. `docs/HANDOFF.md`（このファイル）— 現状把握
2. `docs/PROJECT_RULES.md` — Claude/Codex 共通の遵守ルール（最重要）
3. `CLAUDE.md`（Claude Code）または `AGENTS.md`（Codex）— ツール固有の指示
4. `tasks/current.md` — 進行中タスク（現在は進行中なし。直近の完了は安全な手動再同期支援）
5. `docs/SPEC.md` — 確定/未確定仕様の区別（§3.6 に統合順位予想 ability-v3 を記載）
6. `docs/DECISIONS.md` — 直近の設計判断（2026-07-22: 安全な再同期コマンド提示、展開コメントのゼロコスト既定化、
   Gemini 3.5 Flash移行・環境変数化、comment-v2の馬番号表示、LightGBMモデルLF固定・現行AbilityWeights維持。
   2026-07-21（3）: grade優先のability-v3・確定馬体重の永続化・検証指標。
   2026-07-21: 統合順位予想 Phase1（2軸分類・現データのみ）、確定成績未反映の解決。
   2026-07-20（2）: 切り分け診断ツール導入。
   2026-07-13の2件: 展開恩恵馬frame_noガード追加・自動同期special-entries追加。
   2026-07-12の4件: ingest-status鮮度監視・style-advantage-v1・formation-v1・
   running-style-v2-distance）
7. 必要に応じて `docs/ARCHITECTURE.md`, `docs/adr/0005-rpci-forecast-strategy.md`

## 次の担当者が最初に実行すべきコマンド

```bash
# 1. 最新化・状態確認
git fetch origin && git checkout claude/sweet-einstein-ilnaov && git pull origin claude/sweet-einstein-ilnaov
git log --oneline -10
git status   # クリーンであるはず

# 2. API 健全性確認（新コンテナは依存未インストール。venvを作り .venv/bin 経由で実行する）
cd apps/api
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest -m "not integration" -q   # 464 passed
.venv/bin/ruff check src/ tests/
.venv/bin/lint-imports
.venv/bin/python -m mypy src/ --strict   # ローカルNumPy型定義とPython 3.11設定の不整合に注意

# 3. api-client 型 + Web 健全性確認（新コンテナは node_modules 未インストール）
cd ../../packages/api-client && npm install && npm run typecheck
cd ../../apps/web && npm install && npm run test && npm run typecheck && npm run build

# 4. ingestion-worker 健全性確認（Python 3.12専用。3.12でvenvを作る）
cd ../ingestion-worker
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest tests/ -q   # 185 passed
```

**統合順位予想 Phase2を実データで反映する場合**: ユーザーが Windows 機で
`alembic upgrade head`（migration 003）＋過去 results の再取込が必要（`MANUAL_SYNC_GUIDE.md §7.5`）。
これにより人気・本賞金・grade・確定馬体重が揃う。未実施でも、ability-v3は欠損成分を
自動で除外し、grade欠損時はrace_class推定へ縮退する。
