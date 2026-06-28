<#
.SYNOPSIS
    Windows タスクスケジューラに PCI 取り込みタスクを登録する。

.DESCRIPTION
    管理者権限で実行してください。
    既存の同名タスクは上書き登録されます。

    登録されるタスク:
      PCI_Ingest_Entries  毎日 03:00 JST  出走表取り込み
      PCI_Ingest_Results  毎日 17:30 JST  確定成績取り込み

.EXAMPLE
    # 管理者として PowerShell を開いて実行
    .\scripts\setup_task_scheduler.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$EntriesBat = Join-Path $WorkerDir "scripts\daily_entries.bat"
$ResultsBat  = Join-Path $WorkerDir "scripts\daily_results.bat"

if (-not (Test-Path $EntriesBat) -or -not (Test-Path $ResultsBat)) {
    throw "バッチファイルが見つかりません: $WorkerDir\scripts\"
}

# 現在のログインユーザーでタスクを実行する（パスワード不要・ログオン時のみ動作）
# 無人実行が必要な場合は -RunLevel Highest -User "SYSTEM" に変更する
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

function Register-IngestTask {
    param(
        [string]$TaskName,
        [string]$BatFile,
        [string]$TriggerTime
    )
    $action  = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$BatFile`""
    $trigger = New-ScheduledTaskTrigger -Daily -At $TriggerTime
    $settings = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -RestartCount 0 `
        -MultipleInstances IgnoreNew

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $Principal `
        -Settings $settings `
        -Description "PCI App 自動取り込み: $TaskName" `
        -Force | Out-Null

    Write-Host "登録完了: $TaskName (毎日 $TriggerTime)"
}

Register-IngestTask -TaskName "PCI_Ingest_Entries" -BatFile $EntriesBat -TriggerTime "03:00"
Register-IngestTask -TaskName "PCI_Ingest_Results" -BatFile $ResultsBat  -TriggerTime "17:30"

Write-Host ""
Write-Host "タスクスケジューラへの登録が完了しました。"
Write-Host "確認: Get-ScheduledTask -TaskName 'PCI_Ingest_*' | Select-Object TaskName, State"
