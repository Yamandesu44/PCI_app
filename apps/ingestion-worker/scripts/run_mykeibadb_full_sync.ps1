<#
.SYNOPSIS
    mykeibadb 経由の一気通貫同期（mykeibadb.exe → batch.py）。

.DESCRIPTION
    1. mykeibadb.exe を実行し、JV-Link 経由でローカル MySQL(mykeibadb) を最新化する
       （wmykeibadb.exe で設定済みの mykeibadb.ini を使用）。
       タイムアウト付きで待機する — 「終了時一時停止」が有効なまま無人実行されても
       ハングし続けないようにするための安全策。
    2. batch.py --mode mykeibadb --step entries でPostgreSQLへ出走表を反映する。
    3. batch.py --mode mykeibadb --step results  で確定成績を反映する。

    Windows タスクスケジューラから1日複数回（例: 9/13/18/21時）呼ばれる想定。
    mykeibadb.exe は FROMTIME ウォーターマークで前回からの差分のみ取得するため、
    頻繁に実行しても無駄打ちにならない。

    出走表・特別登録は「今日」時点のレースだけでなく将来レースの分が公開されるため、
    date_from/date_to は「過去7日〜未来14日」の固定ウィンドウで問い合わせる
    （batch.py の既定 --date は「今日1日」のみのため、レンジ指定が必須）。

.PARAMETER TimeoutSeconds
    mykeibadb.exe の最大実行待機秒数（デフォルト 600 = 10分）。
    「終了時一時停止」が有効なままだとここでタイムアウトし強制終了する。

.PARAMETER DaysBack
    取得開始日（今日からの遡り日数。デフォルト 7）。

.PARAMETER DaysForward
    取得終了日（今日からの先送り日数。デフォルト 14）。

.EXAMPLE
    .\run_mykeibadb_full_sync.ps1
#>
param(
    [int]$TimeoutSeconds = 600,
    [int]$DaysBack = 7,
    [int]$DaysForward = 14
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$LogDir    = Join-Path $WorkerDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }
$LogFile = Join-Path $LogDir "$(Get-Date -Format 'yyyyMMdd')-mykeibadb-sync.log"
$EnvFile = Join-Path $WorkerDir ".env"

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# --- .env 読み込み（MYKEIBADB_EXE_PATH 等を環境変数に展開） ---
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

$MykeibadbExe = [System.Environment]::GetEnvironmentVariable("MYKEIBADB_EXE_PATH", "Process")

Write-Log "=== run_mykeibadb_full_sync.ps1 開始 ==="

if (-not $MykeibadbExe -or -not (Test-Path $MykeibadbExe)) {
    Write-Log "ERROR: MYKEIBADB_EXE_PATH が未設定、または mykeibadb.exe が見つかりません: $MykeibadbExe"
    Write-Log "対処: .env に MYKEIBADB_EXE_PATH=C:\...\mykeibadb.exe を設定してください。"
    exit 1
}
$MykeibadbDir = Split-Path $MykeibadbExe -Parent

# --- Step 1: mykeibadb.exe（JV-Link → ローカルMySQL） ---
Write-Log "mykeibadb.exe を起動します（最大 ${TimeoutSeconds}秒待機）: $MykeibadbExe"
$proc = Start-Process -FilePath $MykeibadbExe -WorkingDirectory $MykeibadbDir -WindowStyle Minimized -PassThru
$completed = $proc.WaitForExit($TimeoutSeconds * 1000)

if (-not $completed) {
    Write-Log "ERROR: mykeibadb.exe がタイムアウトしました。強制終了します。"
    Write-Log "対処: wmykeibadb.exe を開き「終了時一時停止」のチェックを外してください。"
    try { $proc.Kill() } catch {}
    exit 1
}
if ($proc.ExitCode -ne 0) {
    Write-Log "WARNING: mykeibadb.exe の終了コードが 0 ではありません: $($proc.ExitCode)"
} else {
    Write-Log "mykeibadb.exe 完了（終了コード 0）"
}

# --- Step 2/3: batch.py（ローカルMySQL → PostgreSQL） ---
$RunBatch = Join-Path $PSScriptRoot "run_batch.ps1"
$DateFrom = (Get-Date).AddDays(-$DaysBack).ToString("yyyyMMdd")
$DateTo   = (Get-Date).AddDays($DaysForward).ToString("yyyyMMdd")

Write-Log "--- 出走表取り込み (batch.py --mode mykeibadb --step entries, $DateFrom→$DateTo) ---"
& $RunBatch -Step entries -Mode mykeibadb -Date $DateFrom -DateTo $DateTo
$entriesExit = $LASTEXITCODE

Write-Log "--- 確定成績取り込み (batch.py --mode mykeibadb --step results, $DateFrom→$DateTo) ---"
& $RunBatch -Step results -Mode mykeibadb -Date $DateFrom -DateTo $DateTo
$resultsExit = $LASTEXITCODE

Write-Log "=== run_mykeibadb_full_sync.ps1 終了 (entries=$entriesExit results=$resultsExit) ==="

if ($entriesExit -ne 0 -or $resultsExit -ne 0) {
    exit 1
}
exit 0
