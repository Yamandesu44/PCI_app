[CmdletBinding()]
param(
    [string]$BindAddress = "127.0.0.1",
    [ValidateRange(1, 65535)]
    [int]$Port = 8000,
    [string]$ApiDirectory = "",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"
$apiRoot = if ([string]::IsNullOrWhiteSpace($ApiDirectory)) {
    Split-Path -Parent $PSScriptRoot
}
else {
    (Resolve-Path -LiteralPath $ApiDirectory).Path
}
$pythonPath = Join-Path $apiRoot ".venv\Scripts\python.exe"
$envPath = Join-Path $apiRoot ".env"

function Get-ApiListenerProcess {
    param([int]$TargetPort)

    $connection = Get-NetTCPConnection -LocalPort $TargetPort -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($null -eq $connection) {
        return $null
    }

    return Get-CimInstance Win32_Process -Filter "ProcessId = $($connection.OwningProcess)"
}

function Test-PciApiProcess {
    param($Process)

    if ($null -eq $Process -or [string]::IsNullOrWhiteSpace($Process.CommandLine)) {
        return $false
    }

    return $Process.CommandLine -match "uvicorn" -and
        $Process.CommandLine -match "pci\.presentation\.app:app"
}

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw "API用Pythonが見つかりません: $pythonPath`n先に apps\api の仮想環境を作成してください。"
}

if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
    throw "API設定ファイルが見つかりません: $envPath`n.env.exampleを基に.envを用意してください。"
}

$listenerProcess = Get-ApiListenerProcess -TargetPort $Port
if ($CheckOnly) {
    if ($null -eq $listenerProcess) {
        Write-Output "STOPPED FastAPIは $BindAddress`:$Port で待受していません。"
        exit 1
    }
    if (-not (Test-PciApiProcess -Process $listenerProcess)) {
        Write-Output "BLOCKED ポート$Portは別のプロセスが使用しています (PID=$($listenerProcess.ProcessId))。"
        exit 2
    }

    try {
        $ready = Invoke-RestMethod -Uri "http://$BindAddress`:$Port/ready" -TimeoutSec 5
    }
    catch {
        Write-Output "ERROR FastAPIのreadinessを取得できません (PID=$($listenerProcess.ProcessId))。"
        exit 3
    }

    if ($ready.status -ne "ready" -or $ready.database -ne "ok") {
        Write-Output "NOT_READY FastAPIは起動中ですが準備未完了です (PID=$($listenerProcess.ProcessId))。"
        exit 4
    }

    try {
        $performance = Invoke-RestMethod `
            -Uri "http://$BindAddress`:$Port/api/v1/forecast-performance?days=180" `
            -TimeoutSec 10
        $requiredFields = @(
            "confidence_review_target",
            "confidence_review_ready",
            "confidence_cohort_groups"
        )
        $missingFields = @(
            $requiredFields | Where-Object { $_ -notin $performance.PSObject.Properties.Name }
        )
        if ($missingFields.Count -gt 0) {
            Write-Output "STALE FastAPIは旧コードです。再起動してください (不足: $($missingFields -join ', '))。"
            exit 5
        }
    }
    catch {
        Write-Output "READY FastAPIとデータベースは利用可能です。認証またはAPIエラーのため契約確認は省略しました (PID=$($listenerProcess.ProcessId))。"
        exit 0
    }

    Write-Output "READY FastAPIとデータベース、および最新の予想検証APIを確認しました (PID=$($listenerProcess.ProcessId))。"
    exit 0
}

if ($null -ne $listenerProcess) {
    if (-not (Test-PciApiProcess -Process $listenerProcess)) {
        throw "ポート$Portは別のプロセスが使用しています (PID=$($listenerProcess.ProcessId))。停止せずに中断します。"
    }

    Write-Output "既存のFastAPIを停止します (PID=$($listenerProcess.ProcessId))。"
    Stop-Process -Id $listenerProcess.ProcessId

    $deadline = (Get-Date).AddSeconds(10)
    do {
        Start-Sleep -Milliseconds 200
        $listenerProcess = Get-ApiListenerProcess -TargetPort $Port
    } while ($null -ne $listenerProcess -and (Get-Date) -lt $deadline)

    if ($null -ne $listenerProcess) {
        throw "ポート$Portの解放を10秒以内に確認できませんでした。"
    }
}

Write-Output "FastAPIを起動します: http://$BindAddress`:$Port"
Write-Output "停止するには、このターミナルで Ctrl+C を押してください。"

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = "src"
    Push-Location $apiRoot
    & $pythonPath -m uvicorn pci.presentation.app:app --host $BindAddress --port $Port
    exit $LASTEXITCODE
}
finally {
    Pop-Location
    $env:PYTHONPATH = $previousPythonPath
}

