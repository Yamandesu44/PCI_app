<#
.SYNOPSIS
    Windows タスクスケジューラに mykeibadb 同期タスクを登録する。

.DESCRIPTION
    管理者権限で実行してください。
    既存の同名タスクは上書き登録されます。

    登録されるタスク:
      PCI_Sync_Mykeibadb  毎日 09:00 / 13:00 / 18:00 / 21:00 JST
        mykeibadb.exe（JV-Link→ローカルMySQL） → batch.py（MySQL→PostgreSQL
        出走表・確定成績）を一気通貫で実行する（scripts\sync_mykeibadb.bat）。

    前提:
      .env に MYKEIBADB_EXE_PATH（mykeibadb.exe のフルパス）が設定済みであること。
      wmykeibadb.exe の「終了時一時停止」チェックが外れていること
      （無人実行時にここでハングするため）。

.EXAMPLE
    # 管理者として PowerShell を開いて実行
    .\scripts\setup_task_scheduler.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WorkerDir = Split-Path $PSScriptRoot -Parent
$SyncBat = Join-Path $WorkerDir "scripts\sync_mykeibadb.bat"

if (-not (Test-Path $SyncBat)) {
    throw "バッチファイルが見つかりません: $SyncBat"
}

# 現在のログインユーザーでタスクを実行する（パスワード不要・ログオン時のみ動作）
# 無人実行が必要な場合は -RunLevel Highest -User "SYSTEM" に変更する
$Principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$Times = @("09:00", "13:00", "18:00", "21:00")
$Triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }

$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$SyncBat`""
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 0 `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "PCI_Sync_Mykeibadb" `
    -Action $action `
    -Trigger $Triggers `
    -Principal $Principal `
    -Settings $settings `
    -Description "PCI App 自動取り込み: mykeibadb.exe → batch.py（1日4回）" `
    -Force | Out-Null

Write-Host "登録完了: PCI_Sync_Mykeibadb (毎日 $($Times -join ' / '))"
Write-Host ""
Write-Host "確認: Get-ScheduledTask -TaskName 'PCI_Sync_Mykeibadb' | Select-Object TaskName, State"
Write-Host "手動テスト起動: Start-ScheduledTask -TaskName 'PCI_Sync_Mykeibadb'"
