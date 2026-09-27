#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: sudo ./scripts/bootstrap-ubuntu.sh [--user USER]

Installs Docker Engine and the Compose plugin from Docker's official Ubuntu repository.
The selected deployment user is added to the docker group and must reconnect afterward.
EOF
}

deployment_user="${SUDO_USER:-}"
while (($#)); do
    case "$1" in
        --user)
            deployment_user="${2:-}"
            shift 2
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
    echo "Run this bootstrap script with sudo" >&2
    exit 1
fi
if [[ -z "$deployment_user" || "$deployment_user" == "root" ]] || ! id "$deployment_user" >/dev/null 2>&1; then
    echo "Select an existing non-root deployment user with --user" >&2
    exit 2
fi
if [[ ! -r /etc/os-release ]]; then
    echo "Unable to identify the operating system" >&2
    exit 1
fi
# shellcheck source=/dev/null
. /etc/os-release
if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "This bootstrap script supports Ubuntu only" >&2
    exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git openssl
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
architecture="$(dpkg --print-architecture)"
codename="${UBUNTU_CODENAME:-$VERSION_CODENAME}"
cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: $codename
Components: stable
Architectures: $architecture
Signed-By: /etc/apt/keyrings/docker.asc
EOF
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
usermod -aG docker "$deployment_user"

echo "Docker and Docker Compose are installed."
echo "Reconnect the SSH session so $deployment_user receives docker-group membership."
echo "Docker-group membership grants root-equivalent access; keep this account protected."
