# ☁️ yuleOSH Cloud Deployment Guide

> **One-command Docker Compose deploy** on Alibaba Cloud (Aliyun), Tencent Cloud, or AWS.
> Includes Caddy HTTPS, database persistence, and backup strategy.

---

## 📋 Prerequisites

| Requirement | Version / Detail |
|-------------|-----------------|
| Docker Engine | ≥ 24.x |
| Docker Compose | ≥ v2.20 (bundled with Docker Desktop) |
| Domain name | A record pointed to your server IP |
| Ports open | 80 (HTTP), 443 (HTTPS), 22 (SSH) |

Cloud firewall / security group rules required:
- **Inbound:** TCP 80, TCP 443, TCP 22 (SSH admin only)

---

## 🚀 One-Command Deploy

### 1. Clone the repository

```bash
git clone <your-repo-url> yuleosh
cd yuleosh
```

### 2. Configure your domain

Edit `deploy/caddy/Caddyfile` and replace `yuleosh.yourdomain.com` with your actual domain:

```bash
sed -i 's/yuleosh.yourdomain.com/your-actual-domain.com/g' deploy/caddy/Caddyfile
```

### 3. (Optional) Enable API key authentication

Uncomment the `YULEOSH_API_KEY` environment variable in `docker-compose.yml`:

```yaml
- YULEOSH_API_KEY=your-very-long-random-api-key-here
```

Generate a strong key:

```bash
openssl rand -hex 32
```

### 4. Launch everything

```bash
docker compose up -d
```

That's it. Caddy automatically:

1. Issues a Let's Encrypt TLS certificate for your domain
2. Proxies HTTPS traffic to yuleOSH on the internal Docker network
3. Redirects HTTP → HTTPS
4. Renews certificates automatically

### 5. Verify

```bash
# Check all services are healthy
docker compose ps

# Check logs
docker compose logs --tail=50 yuleosh
docker compose logs --tail=10 caddy

# Visit your domain in a browser
curl -k https://your-actual-domain.com/api/health
```

Expected health response:

```json
{"status": "ok", "version": "0.1.0", "auth_enabled": true, ...}
```

---

## 🛠️ Cloud-Specific Setup

### Alibaba Cloud (阿里云 ECS)

1. Create an ECS instance with **Ubuntu 22.04 / Debian 12** (2 vCPU, 4 GB RAM minimum)
2. Security Group → add inbound rules:
   - TCP 80 (HTTP)
   - TCP 443 (HTTPS)
   - TCP 22 (SSH, restrict to your IP)
3. Install Docker:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Log out and back in
```

4. Point your domain's A record to the ECS **public IP**
5. Deploy with the one-command flow above

> **DNS Tip:** Alibaba Cloud DNS can manage your domain records. Create an A record → your ECS public IP.

### Tencent Cloud (腾讯云 CVM)

1. Create a CVM instance (Ubuntu 22.04 / Debian 12 recommended)
2. Security Group → inbound:
   - TCP 80, 443, 22
3. Install Docker:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

4. Point your domain A record to the CVM public IP
5. Deploy

> **Note:** Tencent Cloud CVM instances with public IP binding sometimes have the external port mapped from a different internal port. Verify with `curl -4 ifconfig.me`.

### AWS EC2

1. Launch an EC2 instance (t3.small or larger, Ubuntu 24.04 LTS)
2. Security Group → inbound:
   - HTTP (80), HTTPS (443), SSH (22)
3. Attach an **Elastic IP** to the instance (static public IP)
4. Install Docker:

```bash
#!/bin/bash
sudo dnf install -y docker
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in
```

5. Point your domain's A record to the Elastic IP
6. Deploy

> **Optional:** Use AWS Route 53 for managed DNS.

---

## 🔒 Caddy HTTPS Details

Caddy is configured to:

| Feature | Detail |
|---------|--------|
| **Auto TLS** | Let's Encrypt via HTTP-01 challenge (port 80 must be open) |
| **Renewal** | Automatic; Caddy renews certs when >60% of validity remains |
| **Staging** | Uncomment the `tls issuer acme` block in Caddyfile with `acme-staging-v02` to avoid rate limits during testing |
| **Internal/Dev** | Use `tls internal` for self-signed certs on internal networks |
| **Cert storage** | Persisted in Docker volume `caddy_data` — survives container restarts |
| **HTTP→HTTPS** | Automatic — Caddy redirects all :80 traffic to :443 |

### Staging certs (avoid Let's Encrypt rate limits during testing)

```caddyfile
yuleosh.yourdomain.com {
    tls {
        issuer acme {
            dir https://acme-staging-v02.api.letsencrypt.org/directory
        }
    }
    reverse_proxy yuleosh:8080
}
```

Switch back to the production Let's Encrypt URL once everything works.

---

## 🗄️ Database Persistence

yuleOSH stores its data in a SQLite database at `/app/.yuleosh/store.db`.

| Volume/Mount | Purpose | Persistence |
|--------------|---------|-------------|
| `yuleosh_data` | SQLite DB, session state, runtime files | ✅ Survives `docker compose down` |
| `./projects` | User project source code | ✅ On host filesystem |
| `caddy_data` | TLS certificates, ACME account keys | ✅ Survives rebuilds |
| `caddy_config` | Caddy runtime configuration | ✅ Survives rebuilds |

### Data locations summary

| What | Where (inside container) | Docker volume / bind mount |
|------|------------------------|---------------------------|
| SQLite database | `/app/.yuleosh/store.db` | `yuleosh_data` |
| OSH runtime data | `/app/.yuleosh/` | `yuleosh_data` |
| CI results | `/app/.osh/ci/` | `yuleosh_data` |
| Review sessions | `/app/.osh/reviews/` | `yuleosh_data` |
| Evidence packs | `/app/.osh/evidence/` | `yuleosh_data` |
| User projects | `/app/projects/` | `./projects` (host bind) |
| TLS certs | `/data/caddy/` | `caddy_data` |
| Caddy config | `/config/caddy/` | `caddy_config` |

> **Important:** If you run `docker compose down -v`, all volumes (including the database) are **deleted**. Use plain `docker compose down` (no `-v`) to keep data.

---

## 💾 Backup Strategy

### Automated daily backup (recommended)

Create a cron script `/etc/cron.daily/yuleosh-backup`:

```bash
#!/bin/bash
# yuleOSH daily backup — DB, projects, and Caddy certs
BACKUP_DIR="/var/backups/yuleosh"
DATE=$(date +%Y%m%d-%H%M%S)
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

# Backup SQLite database (stop writes for consistency)
docker compose exec -T yuleosh sqlite3 /app/.yuleosh/store.db ".backup /tmp/store-backup.db" 2>/dev/null || \
    docker compose exec -T yuleosh python3 -c "
import shutil; shutil.copy2('/app/.yuleosh/store.db', '/tmp/store-backup.db')
"

docker compose cp yuleosh:/tmp/store-backup.db "$BACKUP_DIR/store-${DATE}.db" 2>/dev/null
docker compose exec yuleosh rm -f /tmp/store-backup.db 2>/dev/null

# Backup Caddy certs (needed for certificate recovery)
docker compose run --rm -v caddy_data:/data alpine tar czf - -C /data caddy \
    > "$BACKUP_DIR/caddy-certs-${DATE}.tar.gz" 2>/dev/null

# Backup projects
tar czf "$BACKUP_DIR/projects-${DATE}.tar.gz" -C "$(dirname $0)/../" projects/ 2>/dev/null

# Rotate old backups (keep 30 days)
find "$BACKUP_DIR" -name "store-*.db" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "caddy-certs-*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "projects-*.tar.gz" -mtime +$RETENTION_DAYS -delete

# Compress yesterday's DB backup
find "$BACKUP_DIR" -name "store-*.db" -mtime +1 -exec gzip {} \;

echo "[yuleOSH Backup] Completed: $(date)"
```

Make it executable:

```bash
sudo chmod +x /etc/cron.daily/yuleosh-backup
```

### Manual backup

```bash
# Create a timestamped backup
DATE=$(date +%Y%m%d)
docker compose exec yuleosh sqlite3 /app/.yuleosh/store.db ".backup /tmp/backup-${DATE}.db"
docker compose cp yuleosh:/tmp/backup-${DATE}.db ./backups/
```

### Restore from backup

```bash
# Stop the service
docker compose down

# Restore database
docker compose run --rm -v yuleosh_data:/data alpine sh -c \
    "cp /data/.yuleosh/store.db /data/.yuleosh/store.db.bak"
docker compose run --rm -v yuleosh_data:/data -v $(pwd)/backups:/backup alpine sh -c \
    "cp /backup/store-YYYYMMDD-HHMMSS.db /data/.yuleosh/store.db"

# Restore Caddy certs
docker compose run --rm -v caddy_data:/data -v $(pwd)/backups:/backup alpine sh -c \
    "cd /data && tar xzf /backup/caddy-certs-YYYYMMDD-HHMMSS.tar.gz"

# Restart
docker compose up -d
```

### Backup to cloud storage (S3 / OSS / COS)

Using `awscli` or cloud CLI tools:

```bash
# Upload to AWS S3
aws s3 sync /var/backups/yuleosh/ s3://my-bucket/yuleosh-backups/

# Upload to Alibaba Cloud OSS
ossutil cp -r /var/backups/yuleosh/ oss://my-bucket/yuleosh-backups/

# Upload to Tencent Cloud COS
coscli sync /var/backups/yuleosh/ cos://my-bucket/yuleosh-backups/
```

Schedule with cron:

```bash
0 3 * * * /path/to/yuleosh-backup.sh && aws s3 sync /var/backups/yuleosh/ s3://my-bucket/yuleosh-backups/
```

---

## 📊 Monitoring

### Health check endpoint

```
GET /api/health → {"status": "ok", ...}
```

Caddy automatically monitors backend health every 30 seconds. Unhealthy backends are removed from the pool.

### Docker health status

```bash
docker compose ps
# Look for "(healthy)" next to each service
```

### Prometheus (optional)

If you have a Prometheus deployment, use the included config:

```bash
docker compose -f deploy/prometheus/prometheus.yml up -d
```

### Logs

```bash
# Caddy access logs (structured JSON)
docker compose exec caddy cat /data/logs/yuleosh-access.log

# Real-time log tailing
docker compose logs -f
```

---

## ⬆️ Updating

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose up -d --build

# Clean up old images
docker image prune -f
```

---

## 🧹 Maintenance Commands

| Command | Purpose |
|---------|---------|
| `docker compose up -d` | Start all services |
| `docker compose down` | Stop (keeps volumes) |
| `docker compose down -v` | **⚠️ Destroys all data volumes** |
| `docker compose logs -f` | Tail logs |
| `docker compose restart yuleosh` | Restart app only |
| `docker compose exec yuleosh python3 yuleosh_cli.py stats` | Run CLI command |
| `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` | Reload Caddy config |

---

## 🔐 Security Checklist

- [ ] `YULEOSH_API_KEY` set to a strong random value
- [ ] Domain DNS A record correctly pointed
- [ ] Port 22 (SSH) restricted to trusted IPs in security group
- [ ] Docker daemon not exposed on TCP (no `-H tcp://0.0.0.0`)
- [ ] Non-root user in container (`USER osh` in Dockerfile) ✓
- [ ] HSTS preload considered for production (see Caddyfile)
- [ ] Regular backups configured
- [ ] OS security updates applied (`apt update && apt upgrade -y`)
