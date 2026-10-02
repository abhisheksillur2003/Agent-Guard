# Phase 16: Windows local operations

Phase 16 packages the local AgentGuard stack into a repeatable Windows workflow. Operators can start, inspect, verify, stop, back up, and restore the product from the repository root without maintaining six separate PowerShell windows.

## Lifecycle commands

`scripts/start-local.ps1` starts Docker Desktop when necessary, brings up PostgreSQL and Redis, waits for PostgreSQL health, applies migrations, and launches the API, Celery worker, Celery scheduler, frontend, and optional Ollama. `-Observability` also starts Grafana, Prometheus, Tempo, and the OpenTelemetry Collector. `-Sync` refreshes Python dependencies.

The launcher records the process ID and exact start time for each process it creates in the ignored `tmp/local` directory. This prevents a reused process ID from causing an unrelated process to be stopped. Existing listeners are left unchanged and must still satisfy the API or frontend readiness check.

`scripts/status-local.ps1` reports managed process state and local listener availability. `scripts/verify-local.ps1` checks frontend HTTP availability, API liveness and database readiness, and Redis. Ollama remains optional. `scripts/stop-local.ps1` stops only matching recorded processes; `-Infrastructure` also stops the PostgreSQL and Redis containers.

## Backup contract

`scripts/backup-local.ps1` uses PostgreSQL's custom archive format. It validates the archive with `pg_restore --list` before copying it to Windows and emits SHA-256 and JSON metadata companions. Backup files are ignored by Git and the archive ACL is restricted to the current Windows identity when possible.

The metadata contains the database name, creation time, format, and checksum. It contains no password, connection URL, access token, signing key, credential, or application payload.

## Restore contract

`scripts/restore-local.ps1` requires `-Force`. It verifies the checksum when available, validates the archive, stops managed application processes, restores into a randomly named staging database, and only then swaps it with the active local database. The previous database remains available until current migrations succeed.

If activation or migration fails, the script terminates connections to the restored database and renames the previous database back into place. This keeps a failed restore from silently replacing usable local data. Unknown API or frontend listeners block restore rather than allowing writes during the swap.

## Security boundaries

All local operations require `AGENTGUARD_ENVIRONMENT=local`; another environment fails closed. Database and role identifiers are validated before they reach PostgreSQL commands. Status output, process arguments, backup metadata, and logs do not include environment secrets. Backups can contain application data and therefore remain local, ignored, and access restricted.

## Completion checks

Phase 16 is complete when PowerShell syntax validation succeeds; cold and repeated startup pass; status and health verification identify all required services; managed shutdown closes API and frontend listeners; a custom-format backup validates; and an isolated database restore preserves a known probe value through the staging swap and migration path.
