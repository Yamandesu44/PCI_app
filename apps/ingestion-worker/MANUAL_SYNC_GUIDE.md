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
2. `batch.py --mode mykeibadb --step entries`（過去7日〜未来14日分の出走表）
3. `batch.py --mode mykeibadb --step results`（同期間の確定成績）

ログは `apps\ingestion-worker\logs\<日付>-mykeibadb-sync.log` に出力される。

---

## 2. 特定の日付範囲だけ取得したい場合

`sync_mykeibadb.bat` は毎回「過去7日〜未来14日」固定だが、特定の期間だけ
ピンポイントで取得・再取得したいときは `batch.py` を直接呼ぶ。

```powershell
cd C:\Users\yuuta\PCI_app\apps\ingestion-worker

# 出走表だけ（例: 7/4〜7/5）
python -m ingestion.batch --mode mykeibadb --step entries --date 20260704 --date-to 20260705

# 確定成績だけ
python -m ingestion.batch --mode mykeibadb --step results --date 20260704 --date-to 20260705

# 出走表・成績まとめて（--step all、日付省略時は今日1日のみ）
python -m ingestion.batch --mode mykeibadb --step all --date 20260704 --date-to 20260705
```

`--date` のみ指定して `--date-to` を省略すると、その1日だけが対象になる。

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

## 8. 更新履歴

| 日付 | 内容 |
|---|---|
| 2026-07-07 | mykeibadb ベースの自動化を構築。MySQL接続・サービスクラッシュ・PCI異常値の3件を調査・修正 |
