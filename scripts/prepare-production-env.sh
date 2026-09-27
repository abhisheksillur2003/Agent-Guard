#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: prepare-production-env.sh --domain HOST --email ADDRESS --image-tag sha-COMMIT [options]

Options:
  --output PATH   Environment file to create (default: .env.production)
  --force         Replace an existing output file
  --help          Show this help
EOF
}

domain=""
email=""
image_tag=""
output_path=".env.production"
force="false"

while (($#)); do
    case "$1" in
        --domain)
            domain="${2:-}"
            shift 2
            ;;
        --email)
            email="${2:-}"
            shift 2
            ;;
        --image-tag)
            image_tag="${2:-}"
            shift 2
            ;;
        --output)
            output_path="${2:-}"
            shift 2
            ;;
        --force)
            force="true"
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

if [[ ! "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || [[ "$domain" != *.* ]]; then
    echo "--domain must be a valid DNS hostname" >&2
    exit 2
fi
if [[ ! "$email" =~ ^[^@[:space:]]+@[^@[:space:]]+\.[^@[:space:]]+$ ]]; then
    echo "--email must be a valid email address" >&2
    exit 2
fi
if [[ ! "$image_tag" =~ ^sha-[0-9a-f]{7,40}$ ]]; then
    echo "--image-tag must identify a verified commit, for example sha-75b6569" >&2
    exit 2
fi
if [[ -z "$output_path" ]]; then
    echo "--output cannot be empty" >&2
    exit 2
fi

for command_name in openssl mktemp; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command is unavailable: $command_name" >&2
        exit 1
    fi
done

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
template_path="$repository_root/.env.production.example"
if [[ "$output_path" != /* ]]; then
    output_path="$repository_root/$output_path"
fi
if [[ -e "$output_path" && "$force" != "true" ]]; then
    echo "$output_path already exists; use --force only when replacement is intentional" >&2
    exit 1
fi
if [[ ! -d "$(dirname "$output_path")" ]]; then
    echo "Output directory does not exist: $(dirname "$output_path")" >&2
    exit 1
fi

new_secret() {
    openssl rand -base64 48 | tr -d '=\n' | tr '+/' '-_'
}

postgres_password="$(new_secret)"
redis_password="$(new_secret)"
auth_signing_key="$(new_secret)"
agent_key_pepper="$(new_secret)"
finding_pepper="$(new_secret)"

umask 077
temporary_path="$(mktemp "${output_path}.tmp.XXXXXX")"
cleanup() {
    rm -f -- "$temporary_path"
}
trap cleanup EXIT

while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    key="${line%%=*}"
    case "$key" in
        DOMAIN) value="$domain" ;;
        ACME_EMAIL) value="$email" ;;
        AGENTGUARD_API_IMAGE)
            value="ghcr.io/abhisheksillur2003/agentguard-api:$image_tag"
            ;;
        AGENTGUARD_FRONTEND_IMAGE)
            value="ghcr.io/abhisheksillur2003/agentguard-frontend:$image_tag"
            ;;
        POSTGRES_PASSWORD) value="$postgres_password" ;;
        REDIS_PASSWORD) value="$redis_password" ;;
        AGENTGUARD_ALLOWED_HOSTS) value="[\"$domain\",\"api\"]" ;;
        AGENTGUARD_DATABASE_URL)
            value="postgresql+asyncpg://agentguard:${postgres_password}@postgres:5432/agentguard"
            ;;
        AGENTGUARD_REDIS_URL)
            value="redis://:${redis_password}@redis:6379/0"
            ;;
        AGENTGUARD_AUTH_SIGNING_KEY) value="$auth_signing_key" ;;
        AGENTGUARD_AGENT_KEY_PEPPER) value="$agent_key_pepper" ;;
        AGENTGUARD_FINDING_FINGERPRINT_PEPPER) value="$finding_pepper" ;;
        *)
            printf '%s\n' "$line" >>"$temporary_path"
            continue
            ;;
    esac
    printf '%s=%s\n' "$key" "$value" >>"$temporary_path"
done <"$template_path"

chmod 600 "$temporary_path"
mv -f -- "$temporary_path" "$output_path"
trap - EXIT
echo "Created $output_path with mode 600 and independent generated secrets."
echo "Keep this file private and back it up separately from the database."
