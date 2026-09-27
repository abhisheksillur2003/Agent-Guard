#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/install-duckdns-updater.sh --subdomain NAME [--force]

Installs a hardened systemd timer that updates NAME.duckdns.org every five minutes.
The DuckDNS token is requested without echo and stored root-only outside the repository.
Use --force only when intentionally replacing an existing DuckDNS configuration.
EOF
}

subdomain=""
force="false"
while (($#)); do
    case "$1" in
        --subdomain)
            subdomain="${2:-}"
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

if ((EUID != 0)); then
    echo "Run this installer with sudo" >&2
    exit 1
fi
if [[ ! "$subdomain" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
    echo "--subdomain must be the lowercase DuckDNS label without .duckdns.org" >&2
    exit 2
fi
if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required" >&2
    exit 1
fi
if [[ -e /etc/agentguard/duckdns.env && "$force" != "true" ]]; then
    echo "DuckDNS configuration already exists; use --force only when replacing it intentionally" >&2
    exit 1
fi

read -r -s -p "DuckDNS token: " duckdns_token
echo
if [[ ! "$duckdns_token" =~ ^[A-Za-z0-9-]{16,128}$ ]]; then
    echo "DuckDNS token has an unexpected format" >&2
    exit 2
fi

install -d -m 700 /etc/agentguard /usr/local/libexec
umask 077
cat >/etc/agentguard/duckdns.env <<EOF
DUCKDNS_SUBDOMAIN=$subdomain
DUCKDNS_TOKEN=$duckdns_token
EOF
chmod 600 /etc/agentguard/duckdns.env
unset duckdns_token

cat >/usr/local/libexec/agentguard-duckdns-update <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

response="$({
    printf 'url = "https://www.duckdns.org/update"\n'
    printf 'get\n'
    printf 'silent\n'
    printf 'show-error\n'
    printf 'fail\n'
    printf 'data-urlencode = "domains=%s"\n' "$DUCKDNS_SUBDOMAIN"
    printf 'data-urlencode = "token=%s"\n' "$DUCKDNS_TOKEN"
    printf 'data-urlencode = "ip="\n'
} | /usr/bin/curl --config -)"

if [[ "$response" != "OK" ]]; then
    echo "DuckDNS update failed" >&2
    exit 1
fi
EOF
chmod 700 /usr/local/libexec/agentguard-duckdns-update

cat >/etc/systemd/system/agentguard-duckdns.service <<'EOF'
[Unit]
Description=Update the AgentGuard DuckDNS record
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
EnvironmentFile=/etc/agentguard/duckdns.env
ExecStart=/usr/local/libexec/agentguard-duckdns-update
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
EOF

cat >/etc/systemd/system/agentguard-duckdns.timer <<'EOF'
[Unit]
Description=Refresh the AgentGuard DuckDNS record every five minutes

[Timer]
OnBootSec=30s
OnUnitActiveSec=5min
RandomizedDelaySec=15s
Persistent=true

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable --now agentguard-duckdns.timer
systemctl start agentguard-duckdns.service
echo "DuckDNS updater installed for ${subdomain}.duckdns.org."
