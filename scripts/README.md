# Scripts

Repository automation scripts belong here. Scripts must avoid embedding credentials and should be safe to run repeatedly.

- `bootstrap-ubuntu.sh` installs Docker Engine and Compose from Docker's official Ubuntu repository.
- `install-duckdns-updater.sh` stores a DuckDNS token root-only and installs a hardened update timer.
- `prepare-production-env.sh` creates a mode-600 production environment with independent random secrets and immutable image tags.
- `deploy-production.sh` validates configuration, pulls or builds images, applies forward-only migrations, and waits for health.
- `verify-production.sh` checks the public HTTPS boundary without requiring or printing credentials.
- The PowerShell preparation and deployment scripts provide the corresponding Windows workflow.

