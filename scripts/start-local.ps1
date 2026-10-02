[CmdletBinding()]
param(
    [switch]$Sync,
    [switch]$Observability,
    [switch]$SkipFrontend,
    [switch]$SkipOllama
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

$root = Get-AgentGuardRepositoryRoot
Set-Location -LiteralPath $root

Assert-AgentGuardLocalEnvironment
$uv = Assert-AgentGuardCommand -Name "uv.exe"
$docker = Assert-AgentGuardCommand -Name "docker.exe"
$pnpm = if ($SkipFrontend) { $null } else { Assert-AgentGuardCommand -Name "pnpm.cmd" }

$dockerReady = $false
try {
    & $docker info --format '{{.ServerVersion}}' *> $null
    $dockerReady = $LASTEXITCODE -eq 0
}
catch {
    $dockerReady = $false
}
if (-not $dockerReady) {
    $dockerDesktop = "C:\Program Files\Docker\Docker\Docker Desktop.exe"
    if (-not (Test-Path -LiteralPath $dockerDesktop -PathType Leaf)) {
        throw "Docker Desktop is not running and its executable was not found."
    }
    Write-Host "Starting Docker Desktop..."
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
    foreach ($attempt in 1..60) {
        Start-Sleep -Seconds 2
        try {
            & $docker info --format '{{.ServerVersion}}' *> $null
            if ($LASTEXITCODE -eq 0) {
                $dockerReady = $true
                break
            }
        }
        catch {
            $dockerReady = $false
        }
    }
    if (-not $dockerReady) {
        throw "Docker Desktop did not become ready within 120 seconds."
    }
}

if ($Sync -or -not (Test-Path -LiteralPath (Join-Path $root ".venv\Scripts\python.exe"))) {
    & $uv sync --all-groups
    if ($LASTEXITCODE -ne 0) {
        throw "Python dependency synchronization failed."
    }
}
if (-not $SkipFrontend -and -not (Test-Path -LiteralPath (Join-Path $root "frontend\node_modules\next"))) {
    & $pnpm --dir frontend install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend dependency installation failed."
    }
}

$composeArguments = @("compose")
if ($Observability) {
    $composeArguments += @("--profile", "observability")
}
$composeArguments += @("up", "-d", "postgres", "redis")
if ($Observability) {
    $composeArguments += @("tempo", "otel-collector", "prometheus", "grafana")
}
& $docker @composeArguments
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose failed to start local infrastructure."
}

$postgresContainer = Get-AgentGuardPostgresContainer
$postgresReady = $false
foreach ($attempt in 1..30) {
    $health = (& $docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' $postgresContainer 2>$null)
    if ($health -eq "healthy") {
        $postgresReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $postgresReady) {
    throw "PostgreSQL did not become healthy within 30 seconds."
}

& $uv run alembic upgrade head
if ($LASTEXITCODE -ne 0) {
    throw "Database migration failed."
}

$stateDirectory = Get-AgentGuardLocalStateDirectory
New-Item -ItemType Directory -Force -Path $stateDirectory | Out-Null
$entries = @(Get-AgentGuardProcesses | Where-Object { Test-AgentGuardRegisteredProcess -Entry $_ })
$python = Join-Path $root ".venv\Scripts\python.exe"

function Start-TrackedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Component,
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$ArgumentList,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory
    )

    if ($entries | Where-Object component -eq $Component) {
        Write-Host "$Component is already managed."
        return
    }
    $stdout = Join-Path $stateDirectory "$Component.stdout.log"
    $stderr = Join-Path $stateDirectory "$Component.stderr.log"
    $process = Start-Process -FilePath $FilePath -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $script:entries += New-AgentGuardProcessEntry -Component $Component -Process $process
    Save-AgentGuardProcesses -Processes $script:entries
}

if (-not (Test-AgentGuardPort -Port 8000)) {
    Start-TrackedProcess -Component "api" -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "backend.app.main:app", "--host", "127.0.0.1", "--port", "8000") `
        -WorkingDirectory $root
}
else {
    Write-Host "API port 8000 is already in use; leaving the existing listener unchanged."
}

Start-TrackedProcess -Component "worker" -FilePath $python `
    -ArgumentList @("-m", "celery", "-A", "backend.app.worker:celery_app", "worker", "--pool=solo", "--loglevel=INFO") `
    -WorkingDirectory $root
Start-TrackedProcess -Component "scheduler" -FilePath $python `
    -ArgumentList @(
        "-m", "celery", "-A", "backend.app.worker:celery_app", "beat", "--loglevel=INFO",
        "--schedule", (Join-Path $stateDirectory "celerybeat-schedule")
    ) `
    -WorkingDirectory $root

if (-not $SkipFrontend) {
    if (-not (Test-AgentGuardPort -Port 3000)) {
        $node = Assert-AgentGuardCommand -Name "node.exe"
        $next = Join-Path $root "frontend\node_modules\next\dist\bin\next"
        Start-TrackedProcess -Component "frontend" -FilePath $node `
            -ArgumentList @($next, "dev", "--hostname", "127.0.0.1", "--port", "3000") `
            -WorkingDirectory (Join-Path $root "frontend")
    }
    else {
        Write-Host "Frontend port 3000 is already in use; leaving the existing listener unchanged."
    }
}

if (-not $SkipOllama -and -not (Test-AgentGuardPort -Port 11434)) {
    $ollamaCommand = Get-Command "ollama.exe" -ErrorAction SilentlyContinue
    if ($null -ne $ollamaCommand) {
        Start-TrackedProcess -Component "ollama" -FilePath $ollamaCommand.Source `
            -ArgumentList @("serve") -WorkingDirectory $root
    }
    else {
        Write-Warning "Ollama is not available in PATH; local AI will remain optional and unavailable."
    }
}

Save-AgentGuardProcesses -Processes $entries

if (-not (Wait-AgentGuardUri -Uri "http://127.0.0.1:8000/readyz" -TimeoutSeconds 60)) {
    throw "The API did not become ready. Check tmp/local/api.stderr.log."
}
if (-not $SkipFrontend -and -not (Wait-AgentGuardUri -Uri "http://127.0.0.1:3000/login" -TimeoutSeconds 90)) {
    throw "The frontend did not become ready. Check tmp/local/frontend.stderr.log."
}

Write-Host "AgentGuard is ready."
Write-Host "Frontend: http://127.0.0.1:3000/login"
Write-Host "API:      http://127.0.0.1:8000"
Write-Host "Status:   .\scripts\status-local.ps1"
