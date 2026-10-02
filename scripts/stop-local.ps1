[CmdletBinding()]
param(
    [switch]$Infrastructure
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

$root = Get-AgentGuardRepositoryRoot
Set-Location -LiteralPath $root
Assert-AgentGuardLocalEnvironment

$entries = @(Get-AgentGuardProcesses)
foreach ($entry in $entries) {
    if (-not (Test-AgentGuardRegisteredProcess -Entry $entry)) {
        continue
    }
    Stop-Process -Id ([int]$entry.pid) -Force
    Write-Host "Stopped $($entry.component) (PID $($entry.pid))."
}
Save-AgentGuardProcesses -Processes @()

if ($Infrastructure) {
    $docker = Assert-AgentGuardCommand -Name "docker.exe"
    & $docker compose stop postgres redis
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose could not stop local infrastructure."
    }
}

Write-Host "Managed AgentGuard processes are stopped."
