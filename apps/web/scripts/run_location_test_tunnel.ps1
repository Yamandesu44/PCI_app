<#
.SYNOPSIS
    少人数ロケテスト用のNext.js本番サーバーとCloudflare Quick Tunnelを起動する。

.DESCRIPTION
    PostgreSQLとFastAPIはlocalhostに残し、共有Basic認証を有効にしたNext.jsだけを
    TryCloudflareの一時URLへ公開する。Ctrl+Cまたはプロセス終了時に子プロセスを停止する。

.PARAMETER EnvFile
    ロケテスト用環境変数ファイル。既定はapps\web\.env.location-test.local。

.PARAMETER Port
    localhostだけで待ち受けるNext.js本番サーバーのポート。既定は3100。

.PARAMETER CloudflaredPath
    cloudflaredコマンド名、またはcloudflared.exeの絶対パス。

.PARAMETER SkipBuild
    直前の本番ビルドを省略する。既存ビルドの再利用時だけ指定する。

.PARAMETER PreflightOnly
    API、設定、依存コマンド、本番ビルドを確認し、公開せず終了する。
#>
param(
    [string]$EnvFile = "",
    [ValidateRange(1024, 65535)]
    [int]$Port = 3100,
    [string]$CloudflaredPath = "cloudflared",
    [switch]$SkipBuild,
    [switch]$PreflightOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$WebDir = Split-Path $PSScriptRoot -Parent
$RepoDir = Split-Path (Split-Path $WebDir -Parent) -Parent
if (-not $EnvFile) {
    $EnvFile = Join-Path $WebDir ".env.location-test.local"
}

function Import-EnvFile {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "設定ファイルがありません: $Path`n.env.location-test.exampleをコピーして値を設定してください。"
    }

    Get-Content -LiteralPath $Path -Encoding UTF8 | ForEach-Object {
        if ($_ -match "^\s*([^#=]+)=(.*)$") {
            $key = $Matches[1].Trim()
            $value = $Matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($key, $value, "Process")
        }
    }
}

function Get-RequiredEnv {
    param([Parameter(Mandatory)][string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "$Name が設定されていません。"
    }
    return $value
}

function Resolve-Executable {
    param(
        [Parameter(Mandatory)][string]$Value,
        [Parameter(Mandatory)][string]$InstallHint
    )

    if ([IO.Path]::IsPathRooted($Value)) {
        if (-not (Test-Path -LiteralPath $Value -PathType Leaf)) {
            throw "実行ファイルがありません: $Value"
        }
        return (Resolve-Path -LiteralPath $Value).Path
    }

    $command = Get-Command $Value -ErrorAction SilentlyContinue
    if (-not $command) {
        throw "$Value が見つかりません。$InstallHint"
    }
    return $command.Source
}

function Test-PortAvailable {
    param([Parameter(Mandatory)][int]$TargetPort)

    $listener = $null
    try {
        $listener = New-Object Net.Sockets.TcpListener([Net.IPAddress]::Loopback, $TargetPort)
        $listener.Start()
    } catch {
        throw "localhost:$TargetPort は使用中です。別の-Portを指定してください。"
    } finally {
        if ($listener) { $listener.Stop() }
    }
}

function Get-AuthorizationHeader {
    param(
        [Parameter(Mandatory)][string]$Username,
        [Parameter(Mandatory)][string]$Password
    )

    $bytes = [Text.Encoding]::UTF8.GetBytes("${Username}:${Password}")
    return "Basic $([Convert]::ToBase64String($bytes))"
}

function Get-HttpStatusCode {
    param([Parameter(Mandatory)]$ErrorRecord)

    $response = $ErrorRecord.Exception.Response
    if ($null -eq $response -or $null -eq $response.StatusCode) {
        return $null
    }
    return [int]$response.StatusCode
}

function Test-ApiReadiness {
    param(
        [Parameter(Mandatory)][string]$ApiBaseUrl,
        [string]$ApiAccessToken
    )

    try {
        $ready = Invoke-RestMethod -Uri "$ApiBaseUrl/ready" -Method Get -TimeoutSec 10
    } catch {
        throw "FastAPIへ接続できません。APIとDocker DBを起動してください。"
    }
    if ($ready.status -ne "ready" -or $ready.database -ne "ok") {
        throw "FastAPI readinessが未完了です: status=$($ready.status) database=$($ready.database)"
    }

    $headers = @{ Accept = "application/json" }
    if ($ApiAccessToken) {
        $headers.Authorization = "Bearer $ApiAccessToken"
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$ApiBaseUrl/api/v1/races?limit=1" `
            -Headers $headers -TimeoutSec 15
    } catch {
        $statusCode = Get-HttpStatusCode -ErrorRecord $_
        if ($statusCode -eq 401 -and -not $ApiAccessToken) {
            throw "FastAPIがBearer認証を要求しています。API_ACCESS_TOKENを設定してください。"
        }
        throw "レース一覧APIを取得できませんでした。FastAPIログを確認してください。"
    }
    if ($response.StatusCode -ne 200) {
        throw "レース一覧APIがHTTP $($response.StatusCode)を返しました。"
    }
}

function Wait-ForLocalWeb {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$Authorization,
        [Parameter(Mandatory)][Diagnostics.Process]$Process
    )

    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($Process.HasExited) {
            throw "Next.jsが起動前に終了しました。apps\web\logsの起動ログを確認してください。"
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Url `
                -Headers @{ Authorization = $Authorization } -TimeoutSec 5
            if ($response.StatusCode -eq 200 -and $response.Content.Contains("レースボード")) {
                return
            }
        } catch {
            # 起動待ち中の接続失敗は次の試行へ進む。
        }
        Start-Sleep -Seconds 1
    }
    throw "Next.jsが30秒以内に応答しませんでした。"
}

function Wait-ForPublicUrl {
    param(
        [Parameter(Mandatory)][string[]]$LogFiles,
        [Parameter(Mandatory)][Diagnostics.Process]$Process
    )

    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($Process.HasExited) {
            throw "cloudflaredがURL発行前に終了しました。apps\web\logsのトンネルログを確認してください。"
        }
        $logText = ""
        foreach ($logFile in $LogFiles) {
            if (Test-Path -LiteralPath $logFile) {
                $logText += Get-Content -LiteralPath $logFile -Raw -Encoding UTF8
            }
        }
        $match = [regex]::Match($logText, "https://[a-z0-9-]+\.trycloudflare\.com")
        if ($match.Success) { return $match.Value }
        Start-Sleep -Seconds 1
    }
    throw "45秒以内にTryCloudflare URLを取得できませんでした。"
}

function Test-PublicWeb {
    param(
        [Parameter(Mandatory)][string]$Url,
        [Parameter(Mandatory)][string]$Authorization,
        [Parameter(Mandatory)][Diagnostics.Process]$Process
    )

    $lastStatus = "接続待ち"
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if ($Process.HasExited) {
            throw "cloudflaredが公開確認中に終了しました。トンネルログを確認してください。"
        }

        $unauthorized = $null
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -MaximumRedirection 0 `
                -TimeoutSec 10 | Out-Null
        } catch {
            $unauthorized = Get-HttpStatusCode -ErrorRecord $_
        }
        $lastStatus = "未認証=$unauthorized"
        if ($unauthorized -eq 401) {
            try {
                $response = Invoke-WebRequest -UseBasicParsing -Uri $Url `
                    -Headers @{ Authorization = $Authorization } -TimeoutSec 20
                $lastStatus = "未認証=401 認証済み=$($response.StatusCode)"
                if (
                    $response.StatusCode -eq 200 -and
                    $response.Content.Contains("レースボード") -and
                    -not $response.Content.Contains("レース一覧を取得できませんでした") -and
                    -not $response.Content.Contains("APIに接続できませんでした")
                ) {
                    return
                }
            } catch {
                $authenticatedStatus = Get-HttpStatusCode -ErrorRecord $_
                $lastStatus = "未認証=401 認証済み=$authenticatedStatus"
            }
        }
        Start-Sleep -Seconds 2
    }
    throw "公開URLを60秒以内に検証できませんでした: $lastStatus"
}

$webProcess = $null
$tunnelProcess = $null
try {
    Import-EnvFile -Path $EnvFile
    $apiBaseUrl = (Get-RequiredEnv -Name "API_BASE_URL").TrimEnd("/")
    $username = Get-RequiredEnv -Name "BETA_ACCESS_USER"
    $password = Get-RequiredEnv -Name "BETA_ACCESS_PASSWORD"
    $apiAccessToken = [Environment]::GetEnvironmentVariable("API_ACCESS_TOKEN", "Process")

    if ($password.Length -lt 16) {
        throw "BETA_ACCESS_PASSWORDは16文字以上にしてください。"
    }
    if ($apiAccessToken -and $password -eq $apiAccessToken) {
        throw "共有パスワードとAPIトークンは別の値にしてください。"
    }

    try {
        $apiUri = [Uri]$apiBaseUrl
    } catch {
        throw "API_BASE_URLが有効なURLではありません。"
    }
    if (-not $apiUri.IsLoopback) {
        throw "Quick Tunnel方式ではAPI_BASE_URLをlocalhostまたは127.0.0.1に限定してください。"
    }

    $cloudflared = Resolve-Executable -Value $CloudflaredPath `
        -InstallHint "Cloudflare公式のWindows版cloudflaredをインストールしてください。"
    $node = Resolve-Executable -Value "node" -InstallHint "Node.jsをインストールしてください。"
    $nextScript = Join-Path $RepoDir "node_modules\next\dist\bin\next"
    if (-not (Test-Path -LiteralPath $nextScript -PathType Leaf)) {
        throw "Next.js依存がありません。リポジトリ直下でnpm ciを実行してください。"
    }

    $cloudflaredConfig = @(
        @(
            (Join-Path $HOME ".cloudflared\config.yml"),
            (Join-Path $HOME ".cloudflared\config.yaml")
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf }
    )
    if ($cloudflaredConfig.Count -gt 0) {
        throw "Quick Tunnelと競合するCloudflare設定があります。公式手順を確認し、公開中だけ別名へ退避してください。"
    }

    Test-ApiReadiness -ApiBaseUrl $apiBaseUrl -ApiAccessToken $apiAccessToken
    Test-PortAvailable -TargetPort $Port
    Write-Host "PASS APIとデータベース"
    Write-Host "PASS 共有認証設定"
    Write-Host "PASS cloudflaredとNode.js"

    if (-not $SkipBuild) {
        Push-Location $RepoDir
        try {
            & npm.cmd run build --workspace=@pci/web
            if ($LASTEXITCODE -ne 0) { throw "Next.js本番ビルドに失敗しました。" }
        } finally {
            Pop-Location
        }
    } elseif (-not (Test-Path -LiteralPath (Join-Path $WebDir ".next\BUILD_ID"))) {
        throw "本番ビルドがありません。-SkipBuildを外して実行してください。"
    }
    Write-Host "PASS Next.js本番ビルド"

    if ($PreflightOnly) {
        Write-Host "ロケテスト公開前のローカル点検に合格しました。公開は開始していません。"
        return
    }

    $logDir = Join-Path $WebDir "logs"
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $webOutLog = Join-Path $logDir "$timestamp-location-web.stdout.log"
    $webErrorLog = Join-Path $logDir "$timestamp-location-web.stderr.log"
    $tunnelOutLog = Join-Path $logDir "$timestamp-location-tunnel.stdout.log"
    $tunnelErrorLog = Join-Path $logDir "$timestamp-location-tunnel.stderr.log"

    $webProcess = Start-Process -FilePath $node -ArgumentList @(
        $nextScript, "start", "--hostname", "127.0.0.1", "--port", "$Port"
    ) -WorkingDirectory $WebDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $webOutLog -RedirectStandardError $webErrorLog

    $authorization = Get-AuthorizationHeader -Username $username -Password $password
    $localUrl = "http://127.0.0.1:$Port/"
    Wait-ForLocalWeb -Url $localUrl -Authorization $authorization -Process $webProcess
    Write-Host "PASS 認証済みNext.js本番サーバー"

    $tunnelProcess = Start-Process -FilePath $cloudflared -ArgumentList @(
        "tunnel", "--url", $localUrl, "--no-autoupdate"
    ) -WorkingDirectory $WebDir -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $tunnelOutLog -RedirectStandardError $tunnelErrorLog

    $publicUrl = Wait-ForPublicUrl -LogFiles @($tunnelOutLog, $tunnelErrorLog) `
        -Process $tunnelProcess
    Test-PublicWeb -Url $publicUrl -Authorization $authorization -Process $tunnelProcess

    Write-Host ""
    Write-Host "ロケテストURL: $publicUrl" -ForegroundColor Green
    Write-Host "未認証401・共有認証200・WebからAPIへの疎通を確認しました。"
    Write-Host "このウィンドウを閉じるかCtrl+Cを押すと公開を終了します。"
    Write-Host "Quick Tunnelはテスト専用です。URLを一般公開しないでください。"

    while (-not $webProcess.HasExited -and -not $tunnelProcess.HasExited) {
        Start-Sleep -Seconds 2
    }
    throw "Webまたはトンネルが予期せず終了しました。logsを確認してください。"
} finally {
    if ($tunnelProcess -and -not $tunnelProcess.HasExited) {
        Stop-Process -Id $tunnelProcess.Id -ErrorAction SilentlyContinue
    }
    if ($webProcess -and -not $webProcess.HasExited) {
        Stop-Process -Id $webProcess.Id -ErrorAction SilentlyContinue
    }
}
