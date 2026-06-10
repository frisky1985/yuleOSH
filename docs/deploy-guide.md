# yuleOSH v0.8.0 — Production Deployment Guide

> SaaS 商业化部署 | 阿里云 ECS / Docker Compose

## Architecture

```
                     ┌─────────────────────────────┐
                     │      Nginx (SSL term)       │
                     │      :443 → :8080           │
                     └──────────┬──────────────────┘
                                │
              ┌─────────────────┼─────────────────┐
              │                 │                 │
     ┌────────▼────────┐ ┌─────▼──────┐ ┌───────▼────────┐
     │  yuleOSH Server │ │  Store.db  │ │  .osh/evidence │
     │  (Python 3.13)  │ │ (SQLite)   │ │  (artifacts)   │
     └─────────────────┘ └────────────┘ └────────────────┘
```

## Docker Compose (Recommended)

```yaml
# docker-compose.yml
version: "3.9"
services:
  yuleosh:
    image: frisky1985/yuleosh:0.8.0
    ports:
      - "8080:8080"
    environment:
      - YULEOSH_JWT_SECRET=${YULEOSH_JWT_SECRET}
      - YULEOSH_API_KEY=${YULEOSH_API_KEY}
      - YULEOSH_NOTIFY_FEISHU_URL=${YULEOSH_NOTIFY_FEISHU_URL}
    volumes:
      - ./data:/app/.yuleosh
      - ./docs:/app/docs
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - yuleosh
```

## Environment Variables

| Variable | Required | Default | Description |
|:---------|:--------:|:--------|:-----------|
| `YULEOSH_JWT_SECRET` | ✅ | auto-gen | JWT signing key (min 32 bytes) |
| `YULEOSH_API_KEY` | - | "" | API key for machine-to-machine auth |
| `YULEOSH_NOTIFY_FEISHU_URL` | - | "" | Feishu webhook URL for CI notifications |
| `OSH_HOME` | - | "/app" | Data directory for DB + evidence |

### Generate secrets

```bash
# Generate a secure JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Or use openssl
openssl rand -base64 32
```

## Nginx SSL Configuration

```nginx
server {
    listen 443 ssl http2;
    server_name yuleosh.example.com;

    ssl_certificate /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;

    # Security headers
    add_header Content-Security-Policy "default-src 'self'" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    location / {
        proxy_pass http://yuleosh:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Quick Start (3 minutes)

```bash
# 1. Clone and build
git clone https://github.com/frisky1985/yuleOSH.git
cd yuleOSH
docker build -t yuleosh:0.8.0 .

# 2. Generate secrets
export YULEOSH_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

# 3. Launch
docker compose up -d

# 4. Verify
curl http://localhost:8080/api/health
# {"status":"ok","version":"0.8.0","tenant_auth":true}
```

## Production Checklist

- [ ] Set `YULEOSH_JWT_SECRET` (min 32 random bytes)
- [ ] Enable HTTPS with valid SSL certificate (Let's Encrypt)
- [ ] Configure firewall (allow only 443, deny 8080 externally)
- [ ] Set up database backup cron: `cp .yuleosh/store.db /backup/$(date +%Y%m%d)/`
- [ ] Configure notify webhook (Feishu/email) for CI alerts
- [ ] Set `YULEOSH_API_KEY` for CI/CD machine auth
- [ ] Monitor: `curl -s http://localhost:8080/api/health` every 30s
