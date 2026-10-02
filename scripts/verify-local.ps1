[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

Assert-AgentGuardLocalEnvironment
$failures = [System.Collections.Generic.List[string]]::new()

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/healthz" -TimeoutSec 5
    if ($health.status -ne "ok" -or $health.environment -ne "local") {
        $failures.Add("API liveness response is not local and healthy.")
    }
}
catch {
    $failures.Add("API liveness endpoint is unavailable.")
}

try {
    $readiness = Invoke-RestMethod -Uri "http://127.0.0.1:8000/readyz" -TimeoutSec 5
    if ($readiness.status -ne "ready" -or $readiness.database -ne "ready") {
        $failures.Add("API readiness or PostgreSQL readiness failed.")
    }
}
catch {
    $failures.Add("API readiness endpoint is unavailable.")
}

try {
    $frontend = Invoke-WebRequest -Uri "http://127.0.0.1:3000/login" -UseBasicParsing -TimeoutSec 10
    if ($frontend.StatusCode -ne 200) {
        $failures.Add("Frontend login page returned HTTP $($frontend.StatusCode).")
    }
}
catch {
    $failures.Add("Frontend login page is unavailable.")
}

if (-not (Test-AgentGuardPort -Port ([int](Get-AgentGuardEnvValue -Name "REDIS_PORT" -Default "6379"))) ) {
    $failures.Add("Redis is not listening.")
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Error $_ }
    exit 1
}

Write-Host "Local verification passed: frontend, API, PostgreSQL, and Redis are ready."
if (Test-AgentGuardPort -Port 11434) {
    Write-Host "Optional Ollama service is listening."
}
else {
    Write-Warning "Optional Ollama service is not listening."
}
