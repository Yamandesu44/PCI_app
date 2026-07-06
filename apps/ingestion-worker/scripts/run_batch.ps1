<#
.SYNOPSIS
    JV-Link 取り込みバッチの実行ラッパー（リトライ + 失敗通知）。

.DESCRIPTION
    Windows タスクスケジューラから呼ばれる。
    指定ステップを最大 $MaxRetries 回試行し、失敗時は NOTIFY_WEBHOOK_URL へ通知する。
    ログは logs\ ディレクトリに日付別ファイルで保存される。

.PARAMETER Step
    実行ステップ: all | masters | entries | results | special-entries

.PARAMETER Mode
    データソース: jvlink | fixture | mykeibadb（デフォルト: jvlink）

.PARAMETER Date
    取得日付 YYYYMMDD（デフォルト: 今日）

.PARAMETER DateTo
    取得終了日付 YYYYMMDD（省略時は --date-to を渡さず、batch.py 側で Date と同じ扱いになる）

.PARAMETER MaxRetries
    最大リトライ回数（デフォルト: 3）

.EXAMPLE
    .\run_batch.ps1 -Step entries
    .\run_batch.ps1 -Step results -Date 20260628
    .\run_batch.ps1 -Step entries -Mode mykeibadb -Date 20260629 -DateTo 20260720
#>
param(
    [Parameter(Mandatory)][string]$Step,
    [string]$Mode = "jvlink",
    [string]$Date = (Get-Date -Format "yyyyMMdd"),
    [string]$DateTo = "",
    [int]$MaxRetries = 3
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- パス解決 ---
$WorkerDir = Split-Path $PSScriptRoot -Parent
$LogDir    = Join-Path $WorkerDir "logs"
if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

$LogFile = Join-Path $LogDir "$Date-$Step.log"
$EnvFile = Join-Path $WorkerDir ".env"

# --- Python 解決（仮想環境優先） ---
$Venv = Join-Path $WorkerDir ".venv\Scripts\python.exe"
$Python = if (Test-Path $Venv) { $Venv } else { "python" }

# --- .env 読み込み（NOTIFY_WEBHOOK_URL を環境変数に展開） ---
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim().Trim('"').Trim("'")
            [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
        }
    }
}

function Write-Log {
    param([string]$Msg)
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

$rangeLabel = if ($DateTo) { "$Date→$DateTo" } else { $Date }
Write-Log "=== run_batch.ps1 開始: step=$Step mode=$Mode date=$rangeLabel ==="

$batchArgs = @("-m", "ingestion.batch", "--mode", $Mode, "--step", $Step, "--date", $Date)
if ($DateTo) { $batchArgs += @("--date-to", $DateTo) }

$attempt = 0
$success = $false

while ($attempt -lt $MaxRetries -and -not $success) {
    $attempt++
    Write-Log "試行 $attempt/$MaxRetries"

    try {
        & $Python @batchArgs 2>&1 |
            Tee-Object -FilePath $LogFile -Append
        if ($LASTEXITCODE -eq 0) {
            $success = $true
            Write-Log "完了 (試行 $attempt 回目)"
        } else {
            Write-Log "失敗 exit=$LASTEXITCODE"
        }
    } catch {
        Write-Log "例外: $_"
    }

    if (-not $success -and $attempt -lt $MaxRetries) {
        $wait = 30 * $attempt
        Write-Log "${wait}秒待機後にリトライします..."
        Start-Sleep -Seconds $wait
    }
}

if (-not $success) {
    $errMsg = "$Step バッチが $MaxRetries 回失敗しました (date=$Date)"
    Write-Log "ERROR: $errMsg"

    # Slack 互換 Webhook 通知
    $webhookUrl = [System.Environment]::GetEnvironmentVariable("NOTIFY_WEBHOOK_URL", "Process")
    if ($webhookUrl) {
        try {
            $body = @{ text = ":x: *ingestion-worker 失敗*`n• step: ``$Step```n• 日付: ``$Date```n• 詳細はログを確認: $LogFile" } |
                ConvertTo-Json -Compress
            Invoke-RestMethod -Uri $webhookUrl -Method Post -Body $body -ContentType "application/json"
            Write-Log "失敗通知を送信しました"
        } catch {
            Write-Log "通知送信失敗: $_"
        }
    }

    exit 1
}

Write-Log "=== run_batch.ps1 終了 ==="
exit 0
