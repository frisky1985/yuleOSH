# yuleOSH 生产部署指南

## 概述

本文档描述 yuleOSH 生产环境的 Docker Compose 部署方案。

### 架构

```
                         ┌─────────────┐
                         │   Nginx     │ ← 端口 80/443 (HTTPS)
                         │  反向代理    │
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │  Backend    │ ← Python HTTP 服务 (端口 8080)
                         │  (app)      │
                         └──────┬──────┘
                                │
                         ┌──────▼──────┐
                         │ PostgreSQL  │ ← 持久化数据库
                         │  (db)       │
                         └─────────────┘

  Certbot (Let's Encrypt) ─── 自动续签 SSL 证书
```

### 前置条件

- Docker Engine ≥ 24.0
- Docker Compose ≥ 2.20
- 域名（已解析到服务器 IP）
- 端口 80/443 开放

---

## 快速部署

### 1. 克隆仓库

```bash
git clone https://github.com/stefanji/yuleOSH.git
cd yuleOSH/deploy
```

### 2. 配置环境变量

```bash
cp .env.production.example .env.production
# 编辑 .env.production，填写以下必要值：
# - YULEOSH_JWT_SECRET
# - STRIPE_SECRET_KEY (如使用 Stripe 支付)
# - YULEOSH_BASE_URL
vim .env.production
```

### 3. 启动服务

```bash
# 初次启动
docker compose -f docker-compose.yml --env-file .env.production up -d

# 查看日志
docker compose -f docker-compose.yml logs -f

# 检查健康状态
curl http://localhost:8080/api/health
```

### 4. 配置 SSL 证书（Let's Encrypt）

```bash
# 首次申请证书（替换为你的域名）
docker compose -f docker-compose.yml run --rm certbot certonly \
  --webroot -w /var/www/html \
  -d yuleosh.yourdomain.com \
  --agree-tos --email admin@yuleosh.com

# 更新 nginx.conf 中的 ssl_certificate 路径，然后重启 nginx
docker compose -f docker-compose.yml restart nginx
```

---

## 环境变量说明

| 变量名 | 必需 | 说明 |
|--------|------|------|
| `YULEOSH_JWT_SECRET` | **是** | JWT 签名密钥。生成：`openssl rand -hex 32` |
| `YULEOSH_BASE_URL` | **是** | 对外访问地址，如 `https://yuleosh.example.com` |
| `YULEOSH_DB_URL` | 否 (默认 SQLite) | PostgreSQL 连接字符串 |
| `STRIPE_SECRET_KEY` | 推荐 | Stripe 密钥，用于支付 |
| `STRIPE_WEBHOOK_SECRET` | 推荐 | Stripe 签名验证密钥 |
| `YULEOSH_NOTIFY_EMAIL_*` | 否 | 邮件通知配置 |
| `YULEOSH_PORT` | 否 | 后端端口（默认 8080） |

完整列表见 `deploy/.env.production.example`

---

## 维护操作

### 查看日志

```bash
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml logs -f nginx
```

### 更新版本

```bash
git pull
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

### 备份数据库

```bash
# PostgreSQL
docker compose -f deploy/docker-compose.yml exec db pg_dump -U yuleosh yuleosh > backup_$(date +%Y%m%d).sql

# SQLite (默认)
cp .yuleosh/store.db backup_$(date +%Y%m%d).db
```

### 健康检查

```bash
curl https://yuleosh.yourdomain.com/api/health
# 预期: {"status": "ok", ...}
```

### 扩缩容

```bash
# 增加后端实例（需配合 nginx upstream）
docker compose -f deploy/docker-compose.yml up -d --scale backend=2
```

### 重置 admin 密码

```bash
# 直接修改数据库
docker compose -f deploy/docker-compose.yml exec db psql -U yuleosh -d yuleosh
UPDATE users SET password_hash = '<new-hash>' WHERE email = 'admin@example.com';
```

---

## 生产安全清单

- [ ] `YULEOSH_JWT_SECRET` 设置为强随机字符串（≥32字节）
- [ ] `YULEOSH_DB_PASSWORD` 设置强密码
- [ ] HTTPS 已启用（Let's Encrypt）
- [ ] Stripe webhook endpoint 已配置 `/api/v1/subscription/webhook`
- [ ] Nginx `server_name` 已修改为实际域名
- [ ] 防火墙仅暴露端口 80/443
- [ ] 定期数据库备份已配置（cron）
- [ ] Docker 日志轮转已设置（10MB max, 3 files）
- [ ] `STRIPE_WEBHOOK_SECRET` 已设置（来自 Stripe Dashboard）
- [ ] `.env.production` 不在版本控制中（已加入 `.gitignore`）

---

## 故障排除

### "Connection refused" 错误

检查 PostgreSQL 是否已就绪：

```bash
docker compose -f deploy/docker-compose.yml logs db
```

### JWT 错误

确认 `YULEOSH_JWT_SECRET` 已设置且没包含特殊字符。

### Stripe Webhook 失败

确认 `STRIPE_WEBHOOK_SECRET` 与 Stripe Dashboard 中 webhook endpoint 的 signing secret 一致。

### 504 Gateway Timeout

Pipeline 运行可能耗时较长。调整 nginx `proxy_read_timeout`：

```nginx
location / {
    proxy_read_timeout 300s;  # 5 分钟
}
```

---

## 参考

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Let's Encrypt 文档](https://letsencrypt.org/docs/)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [yuleOSH GitHub](https://github.com/stefanji/yuleOSH)
