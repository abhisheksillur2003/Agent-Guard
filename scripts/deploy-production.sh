#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: deploy-production.sh [--env-file PATH] [--skip-build]

  --env-file PATH  Production environment file (default: .env.production)
  --skip-build      Pull the immutable API and frontend images instead of building
EOF
}

environment_file=".env.production"
skip_build="false"

while (($#)); do
    case "$1" in
        --env-file)
            environment_file="${2:-}"
            shift 2
            ;;
        --skip-build)
            skip_build="true"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 2
            ;;
    esac
done

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_file="$repository_root/docker-compose.production.yml"
if [[ "$environment_file" != /* ]]; then
    environment_file="$repository_root/$environment_file"
fi
if [[ ! -f "$environment_file" ]]; then
    echo "Production environment file not found: $environment_file" >&2
    exit 1
fi

permissions="$(stat -c '%a' "$environment_file")"
group_permission="${permissions: -2:1}"
other_permission="${permissions: -1}"
if ((10#$group_permission != 0 || 10#$other_permission != 0)); then
    echo "$environment_file must not be readable or writable by group or other users" >&2
    echo "Run: chmod 600 '$environment_file'" >&2
    exit 1
fi
if grep -Eq 'replace-with|agentguard\.example\.com|sha-replace' "$environment_file"; then
    echo "$environment_file still contains deployment placeholders" >&2
    exit 1
fi
if ! grep -Eq '^AGENTGUARD_API_IMAGE=ghcr\.io/abhisheksillur2003/agentguard-api:sha-[0-9a-f]{7,40}$' "$environment_file" || \
    ! grep -Eq '^AGENTGUARD_FRONTEND_IMAGE=ghcr\.io/abhisheksillur2003/agentguard-frontend:sha-[0-9a-f]{7,40}$' "$environment_file"; then
    echo "$environment_file must pin both application images to immutable commit tags" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "Required command is unavailable: docker" >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose plugin is unavailable" >&2
    exit 1
fi

compose=(docker compose --env-file "$environment_file" -f "$compose_file")
export AGENTGUARD_ENV_FILE="$environment_file"

cd "$repository_root"
"${compose[@]}" config --quiet
if [[ "$skip_build" == "true" ]]; then
    "${compose[@]}" pull api frontend postgres redis caddy
else
    "${compose[@]}" build --pull
fi
"${compose[@]}" --profile tools run --rm migrate
"${compose[@]}" up -d --remove-orphans --wait --wait-timeout 180
"${compose[@]}" ps
