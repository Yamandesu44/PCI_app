# 手動データ更新 手順書

Task Scheduler の定期実行（金・土 10:00 / 日 18:00）を待たずに、今すぐ最新データを
取り込みたいときの手順書。トラブルシューティングも含む。

対象読者: 開発者本人（yuuta）。Windows 実行機（`C:\Users\yuuta\PCI_app`）での作業を想定。

---

## 0. 全体の仕組み（おさらい）

```
[wmykeibadb.exe]  … GUI設定ツール。初回設定済みなら普段は触らない
        ↓ (設定を mykeibadb.ini に保存)
[mykeibadb.exe]   … JV-Link経由でローカルMySQL(mykeibadb)を最新化
        ↓
[batch.py --mode mykeibadb]  … MySQL → PostgreSQL（PCI_appの本体DB）
        ↓
Task Scheduler「PCI_Sync_Mykeibadb」が金10:00・土10:00・日18:00に自動実行
```

手動更新は、上記のうち下2段（または全部）を今すぐ実行するだけ。

---

## 1. 通常の手動更新（最も簡単・推奨）

Task Scheduler が実行するのと全く同じ内容を、今すぐ手動で実行する。

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
.\scripts\sync_mykeibadb.bat
```

これで以下が順番に実行される。

1. `mykeibadb.exe` 実行（JV-Link → ローカルMySQL、最大10分待機）
2. `batch.py --mode mykeibadb --step entries`（過去10日〜未来14日分の出走表）
3. `batch.py --mode mykeibadb --step results`（同期間の確定成績）
4. `batch.py --mode mykeibadb --step special-entries`（同期間の重賞等特別登録。
   2026-07-13まで自動実行から漏れていた。詳細は`docs/DECISIONS.md`参照）
5. `batch.py --step forecasts`（今日以降の出走前レース予想を事前生成）

ログは `apps\ingestion-worker\logs\<日付>-mykeibadb-sync.log` に出力される。

### 1.1 Webトップに成績未取込警告が出た場合

警告内の「再同期コマンド」を開くと、DB内の最古の未取込日まで遡る`DaysBack`付きコマンドを
コピーできる。コマンドプロンプトでリポジトリ直下へ移動して実行する。

```cmd
cd C:\Users\yuuta\PCI_app
powershell -ExecutionPolicy Bypass -File apps\ingestion-worker\scripts\run_mykeibadb_full_sync.ps1 -DaysBack 21
```

`21`の部分は画面がデータ状況から算出するため、表示されたコマンドをそのまま使用する。
Web/APIはスクリプトを直接起動せず、実行判断は運用者に残す。

---

## 2. 特定の日付範囲だけ取得したい場合

`sync_mykeibadb.bat` は毎回「過去10日〜未来14日」固定だが、特定の期間だけ
ピンポイントで取得・再取得したいときは `batch.py` を直接呼ぶ。

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker

# 出走表だけ（例: 7/4〜7/5）
python -m ingestion.batch --mode mykeibadb --step entries --date 20260704 --date-to 20260705

# 確定成績だけ
python -m ingestion.batch --mode mykeibadb --step results --date 20260704 --date-to 20260705

# 既存レースの馬場状態・天候だけ（出走馬・成績・予想値は変更しない）
python -m ingestion.batch --mode mykeibadb --step race-metadata --date 20250723 --date-to 20260723 --chunk-days 7

# 重賞等の特別登録だけ（来週分を先取りしたい時。--step all には含まれないので単独指定が必要）
python -m ingestion.batch --mode mykeibadb --step special-entries --date 20260704 --date-to 20260718

# 取り込み済みの今後のレース予想だけを事前生成
python -m ingestion.batch --mode mykeibadb --step forecasts --date 20260704 --date-to 20260718

# 出走表・成績まとめて（--step all、日付省略時は今日1日のみ）
python -m ingestion.batch --mode mykeibadb --step all --date 20260704 --date-to 20260705
```

`--date` のみ指定して `--date-to` を省略すると、その1日だけが対象になる。
`entries`と`results`は、mykeibadbの列分解済みRAに馬場状態・天候があれば通常同期時に自動反映する。
過去に取り込み済みのレースだけを補完する場合は、出走表を再登録しない`race-metadata`を使う。

**注意**: `--step all` は masters/entries/results のみで、`race-metadata`、`special-entries`、
`forecasts`は含まれない。
手動同期ではデータ取込後に上記の順で個別実行する。通常の自動同期スクリプトは両方を実行する。

---

## 3. Task Scheduler のタスクを今すぐ手動起動したい場合

スクリプトを直接叩く代わりに、登録済みタスクをその場で起動することもできる
（内容は 1. と同じ）。

```powershell
Start-ScheduledTask -TaskName "PCI_Sync_Mykeibadb"

# 実行状態・最終結果を確認
Get-ScheduledTaskInfo -TaskName "PCI_Sync_Mykeibadb"
```

---

## 4. 実行結果の確認方法

### ログファイル
`apps\ingestion-worker\logs\` 以下に日付別で保存される。

- `<日付>-mykeibadb-sync.log` … `sync_mykeibadb.bat` 経由の実行ログ（mykeibadb.exe + batch.py 両方）
- `<日付>-entries.log` / `<日付>-results.log` … `run_batch.ps1` 単体で呼んだ場合のログ

正常終了時は末尾がこうなる。

```
=== ingestion-worker 完了 ===
取り込みログ記録: id=NN step=results status=ok
=== run_mykeibadb_full_sync.ps1 end (entries=0 results=0) ===
```

`entries=0 results=0` の `0` は「exit code 0 = 成功」という意味（`1` なら失敗）。

### 取り込みログテーブル（DB）
バッチの成功/失敗履歴は PostgreSQL の `ingest_log` テーブルに残る。API サーバー側で
確認する場合:

```sql
SELECT id, batch_date, step, mode, started_at, finished_at, status, error_msg
FROM ingest_log
ORDER BY id DESC
LIMIT 10;
```

---

## 5. 取り込み済みデータの確認

PCI_app 側 PostgreSQL の状態を集計する診断スクリプトが用意されている。

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
pip install psycopg2-binary python-dotenv   # 初回のみ
python check_data.py          # 全体サマリ
python check_data.py --month  # 月別内訳も表示
```

「出走馬ありレース数」「PCI算出済みエントリ」「RPCI算出済みレース」の件数で、
どこまで取り込めているかざっくり分かる。

---

## 6. よくあるエラーと対処

### 6.1 `Can't connect to MySQL server on 'localhost' ([WinError 10061] 拒否されました)`

MySQL80 サービスが停止している。

```cmd
sc query MySQL80
```

`STATE: STOPPED` なら管理者権限のコマンドプロンプト/PowerShellで起動。

```cmd
net start MySQL80
```

**`WIN32_EXIT_CODE` が `1067` の場合は要注意**（起動しようとしてクラッシュしている状態）。
6.4 を参照。

### 6.2 `Access denied for user 'root'@'localhost' (using password: NO)`

`.env` の `MYKEIBADB_PASSWORD` が空、または実際のMySQLパスワードと不一致。
`wmykeibadb.exe` のGUI画面の「パスワード」欄と同じ値を `.env` に設定する。

```
MYKEIBADB_PASSWORD=（wmykeibadb.exeのパスワード欄と同じ値）
```

### 6.3 `mykeibadb.exe` がいつまでも終わらない（`run_mykeibadb_full_sync.ps1` が10分でタイムアウト）

`wmykeibadb.exe` を開き、「終了時一時停止」のチェックを外す。有効なままだと
無人実行時にキー入力待ちで永久に止まる。

### 6.4 MySQL80 サービスが起動しない（`WIN32_EXIT_CODE: 1067`）

`my.ini` のログファイル名設定が文字化けしていると、MySQLがログファイルを
作成できずに起動失敗することがある（2026-07-07 に実際に発生・解決済み）。

```cmd
type "C:\ProgramData\MySQL\MySQL Server 8.0\my.ini"
```

`general_log_file` / `slow_query_log_file` / `log-error` / `log-bin` の値が
文字化けしていないか確認。文字化けしていたら、管理者権限のNotepadで開いて
以下のようにASCII文字だけの値へ書き換えて保存し、再度 `net start MySQL80`。

```ini
general_log_file="general.log"
slow_query_log_file="slow.log"
log-error="error.log"
log-bin="mysql-bin"
```

### 6.5 PowerShellスクリプトが謎の文字化けエラーで落ちる

`scripts/*.ps1` / `scripts/*.bat` が古い場合に起きていた既知の問題（Windows
PowerShell 5.1 がUTF-8ファイルをANSIコードページで誤読し、`→` 等の記号が
変数名に混入してクラッシュする）。すでに全スクリプトをASCII化して解消済み。
発生した場合はまずリポジトリを最新化する。

```powershell
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
```

### 6.6 特定レースだけ RPCI/PCI3 が異常な値（例: 300超え）になる

上がり3F（`KOHAN_3F`）など元データが物理的にありえない値のとき、
`parse_se_result` が自動的にそのレコードを除外する（2026-07-07 対応済み）。
該当レースは「有効な成績なし」として `RESULT` に確定されず、
既に異常値が入っている場合は API 経由で削除して再取り込みする。

```powershell
Invoke-RestMethod -Uri "http://localhost:8000/internal/ingest/races/<race_key>" -Method Delete

python -m ingestion.batch --mode mykeibadb --step entries --date <対象日> --date-to <対象日>
python -m ingestion.batch --mode mykeibadb --step results --date <対象日> --date-to <対象日>
```

### 6.7 `Get-ScheduledTask` / `Get-Service` などが「認識されていません」

cmd.exe（コマンドプロンプト）で実行している。これらは PowerShell 専用コマンド。
スタートメニューで「PowerShell」を検索して開き直す。cmd.exeのままでよい場合は
以下の代替コマンドを使う。

| PowerShell | cmd.exe代替 |
|---|---|
| `Get-ScheduledTask` | `schtasks /query /tn "タスク名"` |
| `Get-Service` | `sc query サービス名` |
| `Get-ChildItem` | `dir /s /b` |

### 6.8 週明けに土日の結果や来週の特別登録馬が反映されていない

原因は2通りある。切り分けてから対処する。

**(a) 来週の特別登録馬（重賞等の advance entry）が出ない場合**

`run_mykeibadb_full_sync.ps1` が **2026-07-13まで `--step special-entries` を
呼んでいなかった**（`entries`/`results`だけを実行しており、特別登録は別テーブル
`TOKUBETSU_TOROKUBA`/`TOKUBETSU_TOROKUBAGOTO_JOHO` を読む独立ステップのため、
自動実行からは常に漏れていた。`docs/DECISIONS.md` 参照）。修正済みのため、
`git pull` で最新化すれば次回の自動実行から解消する。**今すぐ反映したい場合**は
手動で実行する。

```powershell
cd C:\Users\yuuta\PCI_app
git pull origin claude/sweet-einstein-ilnaov
cd apps\ingestion-worker
python -m ingestion.batch --mode mykeibadb --step special-entries --date <今日> --date-to <2週間後>
```

**(b) 確定成績（`results`）が出ない場合**

`sync_mykeibadb.log` の末尾が `end (entries=0 results=0 special-entries=0)` でも、
この `0` は **exit code（成功=0）であって件数ではない**。「成功しているのに0件」を
そのまま見ても原因が分からないため、以下の順で切り分ける。

1. **まず件数を見る**（2026-07-20〜、`batch.py` が件数ログを出すようになった）。
   `logs\<日付>-mykeibadb-sync.log` に次のような行が出る:
   ```
   確定成績集計 20260712→20260719: SE 1234 行読込 / 確定成績 0 行解析 / 0 レース記録予定
   ```
   - `SE ... 行読込` が **0**: mykeibadb にその期間のデータが無い（未取得）。
     → mykeibadb.exe / JV-Link 側の取得設定・FROMTIME を確認（本リポジトリ外）。
     日付窓の問題の可能性もある（`-DaysBack` を大きくして再実行、下記2）。
   - `SE ... 行読込` が **>0 なのに 確定成績 0 行**: データはあるが確定成績として
     解析できていない。→ **2. の診断ツールで原因を特定する**。

2. **診断ツールで切り分ける**（2026-07-20 追加）:
   ```powershell
   cd apps\ingestion-worker
   python -m ingestion.diagnose_results --date 20260712 --date-to 20260719
   ```
   末尾の「判定」で (A)mykeibadb未取得 /(B)結果列の列名がパーサ候補と不一致 /
   (C)バイト配置バグ のどれかを提示する。出力（件数・DATA_KUBUN分布・**SEテーブルの
   実列名一覧**・判定）を開発担当（Claude/Codex）に共有すれば、(B)/(C) はコード側で
   修正できる。※ 出力には馬名等の個人データは既定で含めない（`--show-values` を付けない限り）。

3. **日付窓の確認**: `run_mykeibadb_full_sync.ps1` は既定で「今日の10日前〜14日後」だけを
   見る。1週間以上前の取りこぼしを埋めるにはバックフィルが要る:
   ```powershell
   .\scripts\run_mykeibadb_full_sync.ps1 -DaysBack 21
   ```

4. 自動実行そのものの失敗を疑う場合: `Get-ScheduledTaskInfo -TaskName "PCI_Sync_Mykeibadb"`
   で `LastTaskResult`/`LastRunTime` を確認（`0`以外や古ければ未発火。PCのスリープ等）。
   `GET /api/v1/ingest-status`（Webトップの鮮度バナー）でも直近の成功/失敗を確認できる。

---

## 7. 関連ファイル一覧

```
apps/ingestion-worker/
├── .env                              # 環境変数（MYKEIBADB_EXE_PATH 等・非コミット）
├── scripts/
│   ├── sync_mykeibadb.bat            # 手動更新の入口（1.で使用）
│   ├── run_mykeibadb_full_sync.ps1   # mykeibadb.exe → batch.py の本体処理
│   ├── run_batch.ps1                 # batch.py 実行ラッパー（リトライ+通知）
│   └── setup_task_scheduler.ps1      # Task Scheduler登録（初回のみ・要管理者）
├── logs/                             # 実行ログ（日付別）
├── check_data.py                     # 取り込み済みデータの集計確認
└── src/ingestion/batch.py            # バッチ本体（--mode/--step/--date の実装）
```

---

## 7.5 Phase2（能力指数 ability-v3）反映のための一度きりの作業（2026-07-21）

統合順位予想の能力指数が「人気・獲得本賞金・正式grade」を使うようになり、確定馬体重もresults再取込で
更新される。既存データには人気・本賞金列が無いため、
**一度だけ** 次を実施する（やらなくても壊れないが、能力指数は従来どおり近走着順のみで動く＝縮退）。

1. DBにカラムを追加（migration 003）:
   ```powershell
   cd C:\Users\yuuta\PCI_app\apps\api
   .venv\Scripts\python -m alembic upgrade head
   ```
2. 過去分の確定成績を再取込（人気・本賞金・grade・確定馬体重を埋める）。反映したい期間を指定して results を回す:
   ```powershell
   cd C:\Users\yuuta\PCI_app\apps\ingestion-worker
   python -m ingestion.batch --mode mykeibadb --step results --date 20250101 --date-to 20261231
   ```
   （既存レースは上書き更新される。以後の通常同期でも自動的に埋まる。）

---

## 8. 更新履歴

| 日付 | 内容 |
|---|---|
| 2026-07-07 | mykeibadb ベースの自動化を構築。MySQL接続・サービスクラッシュ・PCI異常値の3件を調査・修正 |
| 2026-07-13 | ユーザー報告（週明けに土日結果・来週特別登録が未反映）を調査し、`run_mykeibadb_full_sync.ps1`
  が `--step special-entries` を一度も呼んでいなかったバグを発見・修正（6.8節）。 |
| 2026-07-20 | 確定成績が1週間以上未反映の件で、`batch.py` に件数ログを追加し、切り分け診断ツール
  `ingestion.diagnose_results` を新設（6.8(b)節）。`DaysBack` 既定を 7→10 に変更。 |
| 2026-07-21 | 統合順位予想の能力指数 Phase2: 人気・獲得本賞金を永続化（ability-v2）。migration 003 適用と
  過去成績の再取込が必要（7.5節）。 |
| 2026-07-21 | Phase2完成: gradeを正式コードから永続化しability-v3で直接利用。results単独再取込でも
  確定馬体重を更新し、統合順位のバックテスト指標を追加（7.5節）。 |

## 馬場情報補完の補足

`--mode mykeibadb --step all` はmasters/entries/resultsに加えてrace-metadataも実行します。`run_mykeibadb_full_sync.ps1` でもentries後にrace-metadataが自動実行されます。special-entriesとforecastsは引き続き個別ステップです。

旧形式レースキーが残っている環境では、正規キーと同一日付・競馬場・R番号のレースにも馬場情報が反映されます。重複レース自体の削除は行いません。
