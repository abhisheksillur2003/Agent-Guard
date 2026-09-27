# Phase 14: Oracle Always Free deployment path

Phase 14 makes the existing production stack deployable on an ARM-based Oracle Ampere A1 VM without weakening the security boundary. GitHub Actions publishes one immutable image tag containing `linux/amd64` and `linux/arm64` manifests. Docker selects the correct image for the server architecture.

The multi-platform workflow follows Docker's official [multi-platform build guidance](https://docs.docker.com/build/building/multi-platform/) and uses QEMU before Buildx. CI builds both architectures before the publishing workflow can push them to GHCR. Published images retain SBOM and provenance attestations.

## Operator-controlled boundary

Oracle and DuckDNS account creation remains interactive. AgentGuard never requests or stores an Oracle password, payment-card data, SSH private key, or DuckDNS token in the repository. The operator supplies only the public hostname to the application environment.

The server scripts enforce the following boundary:

- `.env.production` is generated with independent secrets and mode `600`.
- API and frontend images use an immutable `sha-<commit>` tag.
- deployment rejects templates that still contain placeholders;
- migrations run before application services and never downgrade automatically;
- Compose waits for service health and keeps PostgreSQL, Redis, and internal APIs off public host ports;
- the DuckDNS token is entered without echo, stored in `/etc/agentguard` with root-only permissions, and omitted from process arguments;
- public verification checks HTTPS, health, readiness, security headers, and restricted routes without accepting credentials.

## Network boundary

Only SSH, HTTP, HTTPS, and optional HTTP/3 traffic enter the VM. SSH should be restricted to the administrator's public address. Caddy terminates HTTPS and routes browser traffic to the frontend and explicitly selected API paths to FastAPI. PostgreSQL, Redis, workers, scheduler, metrics, and API documentation remain on internal Docker networks.

The full operator procedure is in [`../deployment/oracle-always-free.md`](../deployment/oracle-always-free.md).
