param(
    [string]$EnvironmentFile = '.env.production',
    [switch]$SkipBuild
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$composeFile = Join-Path $repositoryRoot 'docker-compose.production.yml'
$resolvedEnvironmentFile = if ([System.IO.Path]::IsPathRooted($EnvironmentFile)) {
    $EnvironmentFile
} else {
    Join-Path $repositoryRoot $EnvironmentFile
}

if (-not (Test-Path -LiteralPath $resolvedEnvironmentFile)) {
    throw "Production environment file not found: $resolvedEnvironmentFile"
}

function Invoke-DockerCompose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)

    & docker compose --env-file $resolvedEnvironmentFile -f $composeFile @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose failed: $($Arguments -join ' ')"
    }
}

Push-Location $repositoryRoot
$previousAgentGuardEnvFile = $env:AGENTGUARD_ENV_FILE
$env:AGENTGUARD_ENV_FILE = $resolvedEnvironmentFile
try {
    Invoke-DockerCompose config --quiet
    if (-not $SkipBuild) {
        Invoke-DockerCompose build --pull
    } else {
        Invoke-DockerCompose pull api frontend
    }
    Invoke-DockerCompose --profile tools run --rm migrate
    Invoke-DockerCompose up -d --remove-orphans
    Invoke-DockerCompose ps
} finally {
    $env:AGENTGUARD_ENV_FILE = $previousAgentGuardEnvFile
    Pop-Location
}
