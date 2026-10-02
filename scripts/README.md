# Scripts

Repository automation scripts belong here. Scripts must avoid embedding credentials and should be safe to run repeatedly.

## Windows local operations

- `start-local.ps1` starts Docker Desktop when needed, PostgreSQL, Redis, migrations, the API, Celery worker and scheduler, frontend, and optional Ollama. Use `-Observability` for Grafana, Prometheus, Tempo, and the OpenTelemetry Collector.
- `status-local.ps1` reports managed process IDs and listening services without reading or printing secrets.
- `verify-local.ps1` checks the frontend, API liveness/readiness, PostgreSQL, and Redis.
- `stop-local.ps1` stops only processes recorded by the local launcher. Add `-Infrastructure` to stop PostgreSQL and Redis containers.
- `backup-local.ps1` creates a validated custom-format PostgreSQL archive plus SHA-256 and metadata companions under the ignored `backups/` directory by default.
- `restore-local.ps1` requires `-Force`, verifies the checksum when present, restores into a staging database, swaps it in only after archive validation, runs forward migrations, and rolls back to the previous database if migration fails.

Local scripts refuse non-local environments. Credentials and environment values are never included in process arguments, status output, or backup metadata.

## Production deployment

- `bootstrap-ubuntu.sh` installs Docker Engine and Compose from Docker's official Ubuntu repository.
- `install-duckdns-updater.sh` stores a DuckDNS token root-only and installs a hardened update timer.
- `prepare-production-env.sh` creates a mode-600 production environment with independent random secrets and immutable image tags.
- `deploy-production.sh` validates configuration, pulls or builds images, applies forward-only migrations, and waits for health.
- `verify-production.sh` checks the public HTTPS boundary without requiring or printing credentials.
- The PowerShell preparation and deployment scripts provide the corresponding Windows workflow.

