# yuleOSH — 生产部署指南

将 yuleOSH SaaS 平台部署到生产环境。假设使用 Docker Compose + Nginx + SSL。

---

## 目录

- [前置条件](#前置条件)
- [快速开始](#快速开始)
- [架构概览](#架构概览)
- [环境变量说明](#环境变量说明)
- [SSL 证书](#ssl-证书)
- [管理命令](#管理命令)
- [健康检查](#健康检查)
- [日志查看](#日志查看)
- [备份策略](#备份策略)
- [监控](#监控)
- [升级](#升级)
- [故障排查](#故障排查)

---

## 前置条件

| 组件 | 版本 | 说明 |
|------|------|------|
| Docker | ≥ 24 | 容器运行时 |
| Docker Compose | ≥ 2.24 | 容器编排 |
| 域名 | 任意 | 指向服务器 IP（默认 `yuleosh.io`）|
| SSL 证书 | Let's Encrypt / 商业 | 443 端口 HTTPS |
| 服务器 | Linux x86_64 | 建议 4 vCPU / 8 GB RAM / 50 GB SSD |

### 系统准备

```bash
# 安装 Docker（Ubuntu/Debian）
curl -fsSL https://get.docker.com | bash

# 安装 Docker Compose Plugin
sudo apt install docker-compose-plugin

# 验证
docker --version && docker compose version
```

---

## 快速开始

### 1. 克隆项目

```bash
git clone <your-repo-url> yuleosh
cd yuleosh
```

### 2. 配置环境变量

```bash
cp deploy/.env.example .env
# 编辑 .env，替换所有 change-me 值
vim .env
```

**必须修改：**
- `PG_PASSWORD` — 数据库密码（强随机）
- `YULEOSH_JWT_SECRET` — JWT 签名密钥（≥32 字符随机串）
- `DOMAIN` — 你的域名

### 3. 获取 SSL 证书

**自动方式（推荐 — 使用 Certbot 容器）：**

```bash
# 先启动 Nginx 但不要挂载 SSL（仅用于 ACME 验证）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d nginx certbot
# 首次获取证书
docker compose exec certbot certbot certonly --webroot \
  --webroot-path=/var/www/certbot \
  -d yuleosh.io
# 证书会写入 deploy/ssl/
```

**手动方式：**

```bash
mkdir -p deploy/ssl
# 将 fullchain.pem 和 privkey.pem 放入 deploy/ssl/
# 或配置反向代理前的负载均衡器处理 SSL
```

### 4. 启动服务

```bash
# 生产模式
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d

# 包含监控（可选）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile monitoring up -d
```

### 5. 验证

```bash
# 查看所有服务状态
docker compose ps

# 检查健康
curl -k https://yuleosh.io/api/health

# 访问前端
open https://yuleosh.io
```

默认管理员账号：`admin@yuleosh.io` / 密码见 `.env` 或 `init-db.sh`

---

## 架构概览

```
┌──────────┐   :443    ┌──────────┐   :3000    ┌──────────┐
│  Browser  │ ─────────▶│  Nginx  │ ─────────▶│ Frontend │
│  Client   │           │ (SSL RP)│            │ (Next.js)│
└──────────┘           └──────────┘            └──────────┘
                              │ :8080                │
                              ▼                      │
                        ┌──────────┐                │
                        │ Backend  │◀───────────────┘
                        │ (Python) │  /api/* (rewrite)
                        └────┬─────┘
                             │ :5432
                             ▼
                        ┌──────────┐
                        │PostgreSQL│
                        │   16     │
                        └──────────┘
```

**请求流程：**

1. 浏览器访问 `https://yuleosh.io`
2. Nginx 终止 SSL，代理到 **Frontend** (`frontend:3000`)
3. 前端 Next.js 渲染 HTML 页面（SSR）
4. 前端通过 Nginx 代理 `/api/*` → **Backend** (`yuleosh:8080`)
5. 后端通过 Docker 网络内联访问 **PostgreSQL** (`postgres:5432`)

---

## 环境变量说明

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `DOMAIN` | ✓ | `yuleosh.io` | 部署域名 |
| `PG_PASSWORD` | ✓ | — | PostgreSQL 密码（强随机）|
| `YULEOSH_JWT_SECRET` | ✓ | — | JWT 签名密钥（≥32 字符）|
| `YULEOSH_BASE_URL` | ✓ | `https://yuleosh.io` | 公开访问 URL |
| `YULEOSH_API_KEY` | — | — | 后端 API 密钥（可选）|
| `YULEOSH_LOG_LEVEL` | — | `info` | 日志级别：`debug`/`info`/`warn`/`error` |
| `YULEOSH_ENV` | ✓ | `production` | 环境标识 |
| `FRONTEND_TAG` | — | `latest` | 前端 Docker 镜像标签 |
| `YULEOSH_TAG` | — | `latest` | 后端 Docker 镜像标签 |
| `STRIPE_SECRET_KEY` | — | — | Stripe 密钥（可选，计费）|
| `STRIPE_WEBHOOK_SECRET` | — | — | Stripe Webhook 密钥 |
| `YULEOSH_NOTIFY_FEISHU_URL` | — | — | 飞书 Webhook URL |
| `YULEOSH_NOTIFY_EMAIL_SMTP` | — | — | SMTP 服务器地址 |
| `YULEOSH_NOTIFY_EMAIL_USER` | — | — | SMTP 用户名 |
| `YULEOSH_NOTIFY_EMAIL_PASS` | — | — | SMTP 密码 |
| `GRAFANA_PASSWORD` | — | `admin` | Grafana 管理员密码 |

> **安全警告：** 生产环境 `.env` 文件必须严格保护：
> - `chmod 600 .env`
> - 不要提交到版本控制（已在 `.gitignore`）
> - 使用密钥管理服务（如 HashiCorp Vault）代替文本文件

---

## SSL 证书

### Let's Encrypt（自动续期）

`certbot` 服务每 12 小时自动检查续期。证书存储在 `deploy/ssl/`。

### 商业证书

去除 `certbot` 服务，将证书文件放入 `deploy/ssl/`：

```bash
deploy/ssl/
├── fullchain.pem    # 证书链
└── privkey.pem      # 私钥
```

### Nginx 内嵌 SSL 终止

如果在 Nginx 前使用负载均衡器或 CDN（如 Cloudflare），可让上游处理 SSL：
- 注释掉 `deploy/nginx.conf` 中的 HTTPS server block
- 仅保留 HTTP server block 并移除 redirect
- 通过 `X-Forwarded-Proto` 头传递协议信息

---

## 管理命令

### 服务生命周期

```bash
# 启动
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d

# 停止
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml stop

# 重启（更新配置后）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml restart

# 查看状态
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml ps

# 完全停止并删除
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml down
```

### 重建服务

```bash
# 仅重建后端
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml build yuleosh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d yuleosh

# 仅重建前端
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml build frontend
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d frontend
```

### 数据库操作

```bash
# 连接数据库
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec postgres psql -U yuleosh -d yuleosh

# 手动备份
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec postgres \
  pg_dump -U yuleosh -d yuleosh --clean --if-exists > backup_$(date +%Y%m%d_%H%M%S).sql

# 手动恢复
cat backup.sql | docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U yuleosh -d yuleosh
```

---

## 健康检查

每个服务都配置了 Docker `healthcheck`。通过以下方式监控：

### HTTP 健康端点

```bash
# API 健康检查
curl -k https://yuleosh.io/api/health
# 预期: {"status":"ok","version":"1.0.0"}

# 前端健康检查
curl -k -o /dev/null -w "%{http_code}" https://yuleosh.io/
# 预期: 200
```

### Docker 健康状态

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml ps
# healthy 列显示各服务状态

# 检查特定服务
docker inspect --format='{{json .State.Health}}' $(docker compose ps -q yuleosh)
```

### 系统健康监控脚本

```bash
#!/bin/bash
# healthcheck.sh — Simple monitoring script
BASE_URL="https://yuleosh.io"

check() {
  local name=$1 url=$2
  if curl -sf "$url" > /dev/null 2>&1; then
    echo "✅ $name — OK"
  else
    echo "❌ $name — DOWN!"
  fi
}

check "Frontend"    "$BASE_URL/"
check "API Health"  "$BASE_URL/api/health"
check "API Version" "$BASE_URL/api/health"
```

---

## 日志查看

```bash
# 实时查看所有服务日志
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f

# 查看特定服务
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f frontend
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f yuleosh
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs -f nginx

# 查看最近 N 行
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs --tail=100 -f yuleosh

# Nginx 访问日志（持久化）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec nginx cat /var/log/nginx/access.log
```

### 集中式日志（生产建议）

对于多节点部署，建议配置：

1. **Docker 日志驱动** → 发送到集中式平台（如 Loki, ELK, Datadog）
2. 修改 `deploy/docker-compose.prod.yml` 添加 logging 配置：

```yaml
x-logging: &default_logging
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"

services:
  yuleosh:
    logging: *default_logging
  frontend:
    logging: *default_logging
```

---

## 备份策略

### 1. PostgreSQL 自动备份

建议设置 cron 任务每日备份：

```bash
# 添加到 crontab（每天凌晨 3:00）
0 3 * * * cd /opt/yuleosh && \
  docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T postgres \
  pg_dump -U yuleosh -d yuleosh --clean --if-exists | gzip > \
  backups/db_$(date +\%Y\%m\%d_\%H\%M\%S).sql.gz && \
  find backups/ -name "db_*.sql.gz" -mtime +30 -delete
```

### 2. 备份清单

| 数据 | 位置 | 备份方式 | 保留时间 |
|------|------|----------|----------|
| PostgreSQL | `pg_data` volume | `pg_dump` | 30 天 |
| 应用数据 | `yuleosh_data` volume | 文件拷贝 | 30 天 |
| SSL 证书 | `deploy/ssl/` | Git / tarball | 持续 |
| .env | 项目根目录 | 密钥管理 | 持续 |

### 3. 完整恢复流程

```bash
# 1. 停止服务
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml down

# 2. 恢复数据库
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d postgres
sleep 10
gunzip -c backups/db_20250101_030000.sql.gz | \
  docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -T postgres \
  psql -U yuleosh -d yuleosh

# 3. 启动所有服务
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d
```

---

## 监控

### Prometheus + Grafana（可选）

启用监控组合：

```bash
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile monitoring up -d
```

- **Prometheus:** `http://localhost:9090` — 指标存储
- **Grafana:** `http://localhost:3001` — 可视化仪表盘（默认密码: `admin`/`admin`）

预置的 Grafana 仪表盘在 `deploy/monitoring/grafana-dashboard.json`。

### 关键指标

| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| CPU 使用率 | 后端/前端容器 | > 80% |
| 内存使用率 | 容器 RSS | > 80% |
| HTTP 5xx 率 | Nginx 响应 | > 1% / 5分钟 |
| API 延迟 P99 | 后端响应时间 | > 2秒 |
| DB 连接数 | PostgreSQL 活动连接 | > 80 |
| 磁盘使用率 | 数据卷 | > 85% |

---

## 升级

### 应用升级

```bash
# 1. 拉取最新代码
git pull origin main

# 2. 检查配置变更
git diff deploy/nginx.conf deploy/docker-compose.prod.yml

# 3. 重新构建并启动
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --build

# 4. 回滚（需要旧镜像）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml up -d --no-build
# 如果之前构建了新镜像，tag 旧版本再启动
docker tag yuleosh-frontend:latest yuleosh-frontend:previous
```

### 数据库迁移

```bash
# 应用端负责迁移（启动时自动运行）
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml logs yuleosh
# 检查日志中的 migration 输出
```

---

## 故障排查

### 常见问题

| 症状 | 可能原因 | 解决 |
|------|----------|------|
| 502 Bad Gateway | 后端未就绪 | 检查 `docker compose ps`，等 `start_period` 过后重试 |
| 503 Service Unavailable | 前端未就绪 | 同上 |
| SSL 错误 | 证书文件缺失 | 确认 `deploy/ssl/fullchain.pem` 存在 |
| 数据库连接拒绝 | 密码/网络错误 | 检查 `.env` 中的 `PG_PASSWORD` |
| 权限被拒 | 数据卷权限 | `chown -R 1001:1001 <volume_path>` |
| /api/health 返回 200 但页面空白 | Next.js SSR 错误 | 查看 `docker compose logs frontend` |

### 调试命令

```bash
# 检查容器的网络连接
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec nginx ping frontend

# 检查 DNS 解析
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec nginx nslookup yuleosh

# 查看环境变量
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec yuleosh env | sort

# 进入容器交互式 shell
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml exec -it yuleosh /bin/bash

# 导出容器指标到 JSON
docker stats --no-stream --format "{{ json . }}"
```

---

## 安全清单

- [ ] `.env` 文件权限设置为 600
- [ ] PostgreSQL 端口仅暴露在 `127.0.0.1`
- [ ] 后端端口仅暴露在 `127.0.0.1`
- [ ] JWT 密钥 ≥ 32 字符（强随机）
- [ ] SSL 证书配置正确（Qualys SSL Test ≥ A）
- [ ] HSTS 已启用
- [ ] CSP 头已配置
- [ ] 定期更新 Docker 镜像
- [ ] 定期备份数据库
- [ ] 启用容器资源限制

---

*最后更新: 2026-06-12*
