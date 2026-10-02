[CmdletBinding()]
param(
    [string]$OutputPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

$root = Get-AgentGuardRepositoryRoot
Set-Location -LiteralPath $root
Assert-AgentGuardLocalEnvironment
$docker = Assert-AgentGuardCommand -Name "docker.exe"
$container = Get-AgentGuardPostgresContainer
$database = Get-AgentGuardEnvValue -Name "POSTGRES_DB" -Default "agentguard"
$databaseUser = Get-AgentGuardEnvValue -Name "POSTGRES_USER" -Default "agentguard"
Assert-AgentGuardDatabaseName -Name $database
Assert-AgentGuardDatabaseName -Name $databaseUser

if (-not $OutputPath) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $OutputPath = Join-Path $root "backups\agentguard-$timestamp.dump"
}
$absoluteOutput = [System.IO.Path]::GetFullPath($OutputPath, $root)
$parent = Split-Path -Parent $absoluteOutput
New-Item -ItemType Directory -Force -Path $parent | Out-Null
if (Test-Path -LiteralPath $absoluteOutput) {
    if (-not $Force) {
        throw "Backup already exists. Choose another path or use -Force."
    }
    if (-not (Test-Path -LiteralPath $absoluteOutput -PathType Leaf)) {
        throw "The backup destination is not a file."
    }
    Remove-Item -LiteralPath $absoluteOutput -Force
}

$temporaryName = "/tmp/agentguard-backup-$([guid]::NewGuid().ToString('N')).dump"
try {
    & $docker exec $container pg_dump --format=custom --no-owner --no-acl `
        --username $databaseUser --dbname $database --file $temporaryName
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL backup failed."
    }
    & $docker exec $container pg_restore --list $temporaryName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL could not validate the generated backup."
    }
    & $docker cp "${container}:${temporaryName}" $absoluteOutput
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not copy the generated backup to Windows."
    }
}
finally {
    & $docker exec $container rm -f $temporaryName *> $null
}

$hash = Get-FileHash -LiteralPath $absoluteOutput -Algorithm SHA256
$hashPath = "$absoluteOutput.sha256"
"$($hash.Hash.ToLowerInvariant())  $([System.IO.Path]::GetFileName($absoluteOutput))" |
    Set-Content -LiteralPath $hashPath -Encoding ascii

$metadata = [ordered]@{
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    database = $database
    format = "postgresql-custom"
    sha256 = $hash.Hash.ToLowerInvariant()
}
$metadata | ConvertTo-Json | Set-Content -LiteralPath "$absoluteOutput.json" -Encoding utf8

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $absoluteOutput /inheritance:r /grant:r "${identity}:(F)" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Warning "The backup was created, but its Windows ACL could not be restricted automatically."
}

Write-Host "Backup created and validated: $absoluteOutput"
Write-Host "SHA-256: $($hash.Hash.ToLowerInvariant())"
