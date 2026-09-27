#!/usr/bin/env bash
set -euo pipefail

if (($# != 1)); then
    echo "Usage: verify-production.sh DOMAIN" >&2
    exit 2
fi
domain="$1"
if [[ ! "$domain" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ ]] || [[ "$domain" != *.* ]]; then
    echo "DOMAIN must be a valid DNS hostname" >&2
    exit 2
fi

base_url="https://$domain"
curl_options=(--silent --show-error --proto '=https' --tlsv1.2 --connect-timeout 10 --max-time 30)
temporary_directory="$(mktemp -d)"
cleanup() {
    rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

curl "${curl_options[@]}" --fail "$base_url/healthz" >"$temporary_directory/health.json"
if ! grep -Eq '"environment"[[:space:]]*:[[:space:]]*"production"' "$temporary_directory/health.json"; then
    echo "Health response does not report the production environment" >&2
    exit 1
fi
curl "${curl_options[@]}" --fail "$base_url/readyz" >/dev/null
curl "${curl_options[@]}" --fail --dump-header "$temporary_directory/headers" \
    --output /dev/null "$base_url/login"

for expected_header in \
    '^strict-transport-security:' \
    '^x-content-type-options:[[:space:]]*nosniff' \
    '^x-frame-options:[[:space:]]*DENY'; do
    if ! grep -Eiq "$expected_header" "$temporary_directory/headers"; then
        echo "Required response header is missing: $expected_header" >&2
        exit 1
    fi
done

for restricted_path in /docs /openapi.json /metrics; do
    status_code="$(curl "${curl_options[@]}" --output /dev/null --write-out '%{http_code}' \
        "$base_url$restricted_path")"
    if [[ "$status_code" != "404" ]]; then
        echo "$restricted_path returned HTTP $status_code instead of 404" >&2
        exit 1
    fi
done

echo "AgentGuard HTTPS, health, readiness, security headers, and restricted routes verified."
