[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
. (Join-Path $PSScriptRoot "local-common.ps1")

if (-not $Force) {
    throw "Restore replaces the local database. Review the backup path and rerun with -Force."
}

$root = Get-AgentGuardRepositoryRoot
Set-Location -LiteralPath $root
Assert-AgentGuardLocalEnvironment
$absoluteBackup = [System.IO.Path]::GetFullPath($BackupPath, $root)
if (-not (Test-Path -LiteralPath $absoluteBackup -PathType Leaf)) {
    throw "Backup file was not found: $absoluteBackup"
}

$checksumPath = "$absoluteBackup.sha256"
if (Test-Path -LiteralPath $checksumPath -PathType Leaf) {
    $expectedHash = ((Get-Content -LiteralPath $checksumPath -Raw).Trim() -split '\s+')[0]
    if ($expectedHash -notmatch '^[a-fA-F0-9]{64}$') {
        throw "The backup checksum file is invalid."
    }
    $actualHash = (Get-FileHash -LiteralPath $absoluteBackup -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "The backup checksum does not match; restore was refused."
    }
}
else {
    Write-Warning "No checksum companion file was found; archive integrity cannot be preverified."
}

& (Join-Path $PSScriptRoot "stop-local.ps1")
if ((Test-AgentGuardPort -Port 8000) -or (Test-AgentGuardPort -Port 3000)) {
    throw "API or frontend listeners remain active. Stop them before restoring the database."
}

$docker = Assert-AgentGuardCommand -Name "docker.exe"
$uv = Assert-AgentGuardCommand -Name "uv.exe"
$container = Get-AgentGuardPostgresContainer
$database = Get-AgentGuardEnvValue -Name "POSTGRES_DB" -Default "agentguard"
$databaseUser = Get-AgentGuardEnvValue -Name "POSTGRES_USER" -Default "agentguard"
Assert-AgentGuardDatabaseName -Name $database
Assert-AgentGuardDatabaseName -Name $databaseUser

$suffix = [guid]::NewGuid().ToString("N").Substring(0, 12)
$stagingDatabase = "ag_restore_$suffix"
$previousDatabase = "ag_previous_$suffix"
$temporaryName = "/tmp/agentguard-restore-$suffix.dump"
$switched = $false

try {
    & $docker cp $absoluteBackup "${container}:${temporaryName}"
    if ($LASTEXITCODE -ne 0) {
        throw "Docker could not copy the backup into PostgreSQL."
    }
    & $docker exec $container pg_restore --list $temporaryName *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL rejected the backup archive."
    }
    & $docker exec $container createdb --username $databaseUser $stagingDatabase
    if ($LASTEXITCODE -ne 0) {
        throw "Could not create the staging restore database."
    }
    & $docker exec $container pg_restore --exit-on-error --no-owner --no-acl `
        --username $databaseUser --dbname $stagingDatabase $temporaryName
    if ($LASTEXITCODE -ne 0) {
        throw "PostgreSQL restore failed before the active database was changed."
    }

    $terminateTarget = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database' AND pid <> pg_backend_pid();"
    & $docker exec $container psql --username $databaseUser --dbname postgres `
        --set ON_ERROR_STOP=1 --command $terminateTarget *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Could not close existing local database connections."
    }
    & $docker exec $container psql --username $databaseUser --dbname postgres `
        --set ON_ERROR_STOP=1 --command "ALTER DATABASE `"$database`" RENAME TO `"$previousDatabase`";"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not preserve the previous local database."
    }
    & $docker exec $container psql --username $databaseUser --dbname postgres `
        --set ON_ERROR_STOP=1 --command "ALTER DATABASE `"$stagingDatabase`" RENAME TO `"$database`";"
    if ($LASTEXITCODE -ne 0) {
        & $docker exec $container psql --username $databaseUser --dbname postgres `
            --command "ALTER DATABASE `"$previousDatabase`" RENAME TO `"$database`";" *> $null
        throw "Could not activate the restored local database."
    }
    $switched = $true

    & $uv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "The restored database could not be migrated to the current schema."
    }
    & $docker exec $container dropdb --force --if-exists --username $databaseUser $previousDatabase
    if ($LASTEXITCODE -ne 0) {
        throw "Restore succeeded, but the previous temporary database could not be removed."
    }
    $switched = $false
}
catch {
    if ($switched) {
        $terminateRestored = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$database' AND pid <> pg_backend_pid();"
        & $docker exec $container psql --username $databaseUser --dbname postgres `
            --command $terminateRestored *> $null
        & $docker exec $container dropdb --force --if-exists --username $databaseUser $database *> $null
        & $docker exec $container psql --username $databaseUser --dbname postgres `
            --command "ALTER DATABASE `"$previousDatabase`" RENAME TO `"$database`";" *> $null
    }
    else {
        & $docker exec $container dropdb --force --if-exists --username $databaseUser $stagingDatabase *> $null
    }
    throw
}
finally {
    & $docker exec $container rm -f $temporaryName *> $null
}

Write-Host "Local database restored and migrated successfully."
Write-Host "Restart AgentGuard with .\scripts\start-local.ps1"
