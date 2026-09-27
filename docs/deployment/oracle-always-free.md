# Oracle Always Free and DuckDNS deployment

This guide creates the external infrastructure required by AgentGuard without purchasing a server or domain. Oracle account verification and DuckDNS login are personal operations; do not paste their passwords, card information, SSH private keys, or DuckDNS token into AgentGuard, Git, an issue, or a chat.

Oracle documents the Always Free Ampere allowance as up to 2 OCPUs and 12 GB RAM, subject to regional capacity and idle-instance reclamation. Choose the home region carefully because Always Free compute must be created there. Review the current [Oracle Free Tier documentation](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm) and [Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm) before creating resources.

DuckDNS provides a free subdomain that points to the VM's public address. Its [service explanation](https://www.duckdns.org/why.jsp) and [update documentation](https://www.duckdns.org/install.jsp) describe the DNS record and update token used below.

## 1. Create the Oracle VM

In the Oracle Cloud console:

1. Create an **Always Free eligible** compute instance in the account's home region.
2. Select an Ubuntu image and the **VM.Standard.A1.Flex** shape.
3. Allocate **2 OCPUs and 12 GB RAM**.
4. Use a boot volume within the account's Always Free storage allowance. A 75–100 GB volume provides practical room for images, logs, and database backups.
5. Place the VM in a public subnet and assign a public IPv4 address.
6. Add your SSH public key. Downloaded private keys stay only on your computer.

Create network ingress rules for:

| Protocol | Port | Source | Purpose |
| --- | ---: | --- | --- |
| TCP | 22 | Your current public IP with `/32` | SSH administration |
| TCP | 80 | `0.0.0.0/0` | Certificate issuance and HTTP redirect |
| TCP | 443 | `0.0.0.0/0` | HTTPS application traffic |
| UDP | 443 | `0.0.0.0/0` | Optional HTTP/3 traffic |

Do not add public rules for PostgreSQL 5432, Redis 6379, FastAPI 8000, or monitoring ports.

## 2. Connect from Windows

From PowerShell, substitute the private-key path and public IP shown by Oracle:

```powershell
ssh -i "$HOME\.ssh\agentguard-oracle.key" ubuntu@203.0.113.10
```

The remaining commands in this guide run inside the Ubuntu SSH session.

## 3. Check out a verified revision and install Docker

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/abhisheksillur2003/Agent-Guard.git
cd Agent-Guard
git checkout main
git status --short --branch
sudo ./scripts/bootstrap-ubuntu.sh
```

Disconnect and reconnect after the bootstrap script so the `ubuntu` account receives Docker-group membership. Docker-group membership grants root-equivalent access, so protect the SSH key and account.

Confirm the installation:

```bash
docker version
docker compose version
uname -m
```

The architecture should report `aarch64` on the Ampere VM.

## 4. Create the free hostname

Sign in to [DuckDNS](https://www.duckdns.org/), choose an unused lowercase subdomain such as `my-agentguard`, and create it. The final hostname will be `my-agentguard.duckdns.org`.

Install the updater from the repository. Enter the DuckDNS token only at the hidden prompt:

```bash
sudo ./scripts/install-duckdns-updater.sh --subdomain my-agentguard
```

Verify the timer and DNS record:

```bash
systemctl status agentguard-duckdns.timer --no-pager
getent hosts my-agentguard.duckdns.org
```

The resolved IPv4 address must match the VM's public address before deployment. Never add `/etc/agentguard/duckdns.env` to Git or copy its contents into chat.

## 5. Enable the Ubuntu firewall

Allow SSH before enabling the firewall so the current session is not locked out:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status verbose
```

Both Oracle's network rules and Ubuntu's firewall must allow a public port before it is reachable.

## 6. Generate production configuration

Use the current checked-out commit to select the matching immutable image tag:

```bash
git pull --ff-only origin main
IMAGE_TAG="sha-$(git rev-parse --short=7 HEAD)"
./scripts/prepare-production-env.sh \
  --domain my-agentguard.duckdns.org \
  --email your-email@example.com \
  --image-tag "$IMAGE_TAG"
```

The generator creates `.env.production` with independent secrets, the verified API and frontend image tags, and mode `600`. Back up this file in an encrypted location separate from database backups. Do not print or commit it.

## 7. Deploy AgentGuard

```bash
./scripts/deploy-production.sh --skip-build
```

The command validates configuration, pulls the ARM64 variants, applies migrations, starts all services, and waits for health checks. Inspect the stack without printing the environment:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml ps
docker compose --env-file .env.production -f docker-compose.production.yml \
  logs --tail 100 api frontend caddy worker scheduler
```

Caddy obtains the HTTPS certificate after DNS points to the VM and ports 80 and 443 are reachable.

## 8. Create the production administrator

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec api \
  agentguard-admin create-admin \
  --organization "AgentGuard Production" \
  --slug agentguard-production \
  --email your-email@example.com
```

Enter a unique password at the hidden prompts. Do not reuse the local-development password.

## 9. Verify the public deployment

```bash
./scripts/verify-production.sh my-agentguard.duckdns.org
```

Then open `https://my-agentguard.duckdns.org/login` from your Windows browser and sign in with the production administrator. Confirm from an external network that ports 5432, 6379, and 8000 are unreachable.

## 10. Keep the free deployment healthy

- Stay within resources marked **Always Free eligible** and configure billing alerts in Oracle.
- Oracle may reclaim qualifying idle Always Free compute. Review the current idle-instance policy in the Always Free documentation.
- Create encrypted off-server PostgreSQL backups and test restoration.
- Back up `.env.production` separately. Losing its peppers invalidates existing agent credentials and finding fingerprints.
- Before an update, back up the database, check out the reviewed commit, regenerate only the image-tag lines or update them carefully, and run the deployment script. Never automatically downgrade the database.
- Ollama remains disabled in the production template because model inference competes with the application stack for the VM's limited CPU and memory.
