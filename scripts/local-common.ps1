Set-StrictMode -Version Latest

$script:RepositoryRoot = Split-Path -Parent $PSScriptRoot
$script:LocalStateDirectory = Join-Path $script:RepositoryRoot "tmp\local"
$script:LocalProcessFile = Join-Path $script:LocalStateDirectory "processes.json"

function Get-AgentGuardRepositoryRoot {
    return $script:RepositoryRoot
}

function Get-AgentGuardLocalStateDirectory {
    return $script:LocalStateDirectory
}

function Get-AgentGuardEnvValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Default = ""
    )

    $processValue = [Environment]::GetEnvironmentVariable($Name, "Process")
    if (-not [string]::IsNullOrWhiteSpace($processValue)) {
        return $processValue
    }

    $envPath = Join-Path $script:RepositoryRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        return $Default
    }
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*#' -or $line -notmatch '=') {
            continue
        }
        $parts = $line -split '=', 2
        if ($parts[0].Trim() -ne $Name) {
            continue
        }
        $value = $parts[1].Trim()
        if (
            $value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'")))
        ) {
            return $value.Substring(1, $value.Length - 2)
        }
        return $value
    }
    return $Default
}

function Assert-AgentGuardLocalEnvironment {
    $environment = Get-AgentGuardEnvValue -Name "AGENTGUARD_ENVIRONMENT" -Default "local"
    if ($environment -ne "local") {
        throw "Local operations require AGENTGUARD_ENVIRONMENT=local."
    }
}

function Assert-AgentGuardCommand {
    param([Parameter(Mandatory = $true)][string]$Name)

    $command = Get-Command $Name -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Required command '$Name' was not found in PATH."
    }
    return $command.Source
}

function Test-AgentGuardPort {
    param([Parameter(Mandatory = $true)][int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $connection = $client.ConnectAsync("127.0.0.1", $Port)
        if (-not $connection.Wait(500)) {
            return $false
        }
        return $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-AgentGuardUri {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                return $true
            }
        }
        catch {
            Start-Sleep -Milliseconds 750
        }
    }
    return $false
}

function Get-AgentGuardProcesses {
    if (-not (Test-Path -LiteralPath $script:LocalProcessFile -PathType Leaf)) {
        return @()
    }
    try {
        $items = @(Get-Content -LiteralPath $script:LocalProcessFile -Raw | ConvertFrom-Json)
        return @($items)
    }
    catch {
        throw "The local process registry is invalid: $script:LocalProcessFile"
    }
}

function Save-AgentGuardProcesses {
    param([Parameter(Mandatory = $true)][AllowEmptyCollection()][object[]]$Processes)

    New-Item -ItemType Directory -Force -Path $script:LocalStateDirectory | Out-Null
    ConvertTo-Json -InputObject @($Processes) -Depth 4 |
        Set-Content -LiteralPath $script:LocalProcessFile -Encoding utf8
}

function Test-AgentGuardRegisteredProcess {
    param([Parameter(Mandatory = $true)][object]$Entry)

    $process = Get-Process -Id ([int]$Entry.pid) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $false
    }
    try {
        $expectedStart = ([datetime]$Entry.started_at).ToUniversalTime()
        return $process.StartTime.ToUniversalTime().Ticks -eq $expectedStart.Ticks
    }
    catch {
        return $false
    }
}

function New-AgentGuardProcessEntry {
    param(
        [Parameter(Mandatory = $true)][string]$Component,
        [Parameter(Mandatory = $true)][System.Diagnostics.Process]$Process
    )

    return [pscustomobject]@{
        component = $Component
        pid = $Process.Id
        started_at = $Process.StartTime.ToUniversalTime().ToString("o")
    }
}

function Assert-AgentGuardDatabaseName {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($Name -notmatch '^[A-Za-z_][A-Za-z0-9_]*$') {
        throw "Database and user names must contain only letters, digits, and underscores."
    }
}

function Get-AgentGuardPostgresContainer {
    $containerId = (docker compose ps -q postgres).Trim()
    if (-not $containerId) {
        throw "The AgentGuard PostgreSQL container is not running."
    }
    return $containerId
}
