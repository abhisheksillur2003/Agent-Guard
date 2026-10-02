[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

$root = Get-AgentGuardRepositoryRoot
Set-Location -LiteralPath $root
Assert-AgentGuardLocalEnvironment

$registered = @(Get-AgentGuardProcesses)
$components = foreach ($name in @("api", "frontend", "worker", "scheduler", "ollama")) {
    $entry = $registered | Where-Object component -eq $name | Select-Object -First 1
    [pscustomobject]@{
        Component = $name
        Managed = $null -ne $entry
        Running = $null -ne $entry -and (Test-AgentGuardRegisteredProcess -Entry $entry)
        PID = if ($null -ne $entry) { [int]$entry.pid } else { $null }
    }
}
$components | Format-Table -AutoSize

$checks = @(
    [pscustomobject]@{ Service = "Frontend"; Address = "http://127.0.0.1:3000/login"; Ready = Test-AgentGuardPort -Port 3000 },
    [pscustomobject]@{ Service = "API"; Address = "http://127.0.0.1:8000/readyz"; Ready = Test-AgentGuardPort -Port 8000 },
    [pscustomobject]@{ Service = "PostgreSQL"; Address = "localhost:$(Get-AgentGuardEnvValue -Name 'POSTGRES_PORT' -Default '5432')"; Ready = Test-AgentGuardPort -Port ([int](Get-AgentGuardEnvValue -Name "POSTGRES_PORT" -Default "5432")) },
    [pscustomobject]@{ Service = "Redis"; Address = "localhost:$(Get-AgentGuardEnvValue -Name 'REDIS_PORT' -Default '6379')"; Ready = Test-AgentGuardPort -Port ([int](Get-AgentGuardEnvValue -Name "REDIS_PORT" -Default "6379")) },
    [pscustomobject]@{ Service = "Ollama"; Address = "http://127.0.0.1:11434"; Ready = Test-AgentGuardPort -Port 11434 }
)
$checks | Format-Table -AutoSize

$missingRequired = @(
    $checks |
        Where-Object Service -in @("Frontend", "API", "PostgreSQL", "Redis") |
        Where-Object { -not $_.Ready }
)
if ($missingRequired.Count -gt 0) {
    exit 1
}
