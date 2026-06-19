# yuleOSH 生产部署指南 v2.1

## 概述

本文档描述 yuleOSH 生产环境的完整部署方案，涵盖 Docker Compose + Nginx/Caddy +
Let's Encrypt 自动 HTTPS。

### 架构

```
                  ┌──────────────┐
                  │   DNS: A记录  │
                  │ yuleosh.io ◄── 服务器公网 IP
                  └──────┬───────┘
                         │
              ┌──────────▼──────────┐
              │  Nginx / Caddy      │ ← 端口 80/443 (HTTPS)
              │  反向代理 + SSL     │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  Backend (Python)   │ ← JSON API (端口 8080)
              │  yuleosh 核心服务   │
              └──────────┬──────────┘
                         │
              ┌──────────▼──────────┐
              │  PostgreSQL 16      │ ← 持久化数据库
              │  (多租户存储)       │
              └─────────────────────┘

  Certbot (Let's Encrypt) ─── 自动续签 SSL 证书 (每12小时)
  Prometheus + Grafana ──── 可观测性 (可选, monitoring profile)
```

### 前置条件

- 服务器：Linux x86_64 / ARM64 (2C4G 最低推荐)
- Docker Engine ≥ 24.0
- Docker Compose ≥ 2.20
- 域名（已解析到服务器 IP）
- 端口 80/443 开放

---

## 1. 域名 + DNS 配置

### 1.1 注册 / 准备域名

在域名注册商（阿里云/腾讯云/Cloudflare）购买域名，例如 `yuleosh.io`。

### 1.2 添加 DNS A 记录

登录 DNS 管理面板，添加一条 **A 记录**：

| 记录类型 | 主机记录 | 记录值 | TTL |
|:---------|:---------|:-------|:----|
| A | @ | `<服务器公网 IP>` | 600 |
| A | www | `<服务器公网 IP>` | 600 |
| A | api | `<服务器公网 IP>` | 600 |

验证 DNS 解析：

```bash
dig +short yuleosh.io
dig +short www.yuleosh.io
dig +short api.yuleosh.io
```

预期输出为你的服务器 IP。

### 1.3 配置 Nginx server_name

> 如果使用 Caddy（自动 HTTPS），跳到 §1.4

编辑 `deploy/nginx/nginx.conf`，替换所有 `yuleosh.yourdomain.com` 为你的实际域名：

```nginx
server_name yuleosh.io www.yuleosh.io;
```

### 1.4 配置 Caddy（可选，替代 Nginx）

如果选择 Caddy 而非 Nginx，编辑 `deploy/caddy/Caddyfile`：

```
yuleosh.io {
    reverse_proxy /api/* yuleosh:8080
    reverse_proxy yuleosh:3000
}
```

Caddy 自动处理 SSL 颁发和续签，无需手动运行 certbot。

---

## 2. SSL / HTTPS 配置

### 2.1 方式 A：Nginx + Certbot（推荐）

#### 初次申请证书

```bash
# 确保 Nginx 已运行
docker compose -f deploy/docker-compose.yml up -d nginx

# 申请证书（替换为你的域名 + 邮箱）
docker compose -f deploy/docker-compose.yml run --rm certbot certonly \
  --webroot -w /var/www/html \
  -d yuleosh.io \
  -d www.yuleosh.io \
  --agree-tos --email admin@yuleosh.com

# 证书路径：
#   /etc/letsencrypt/live/yuleosh.io/fullchain.pem
#   /etc/letsencrypt/live/yuleosh.io/privkey.pem
```

#### 自动续签

Certbot 容器每 12 小时自动检查续签（已配置在 docker-compose.yml 中）。

#### 验证 HTTPS

```bash
curl -I https://yuleosh.io
# 预期: HTTP/2 200
#        strict-transport-security: max-age=63072000
```

### 2.2 方式 B：Caddy 自动 HTTPS

Caddy 在首次请求时自动向 Let's Encrypt 申请证书。只需确保：

1. 域名 A 记录已正确解析到服务器
2. 端口 80 和 443 已开放
3. 启动 Caddy 后等待 10-30 秒即可

```bash
# 直接使用 Caddy 版本
docker compose -f deploy/docker-compose.prod.yml up -d nginx
# 其中 nginx 镜像替换为 caddy（或单独运行 Caddy 容器）
```

### 2.3 方式 C：自签名证书（内部/测试环境）

```bash
# 生成自签名证书（有效期 365 天）
mkdir -p deploy/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout deploy/ssl/yuleosh.key \
  -out deploy/ssl/yuleosh.crt \
  -subj "/C=CN/ST=Shanghai/O=yuleOSH/CN=yuleosh.local"

# 在 nginx.conf 中使用：
#   ssl_certificate /etc/nginx/ssl/yuleosh.crt;
#   ssl_certificate_key /etc/nginx/ssl/yuleosh.key;
```

---

## 3. 环境变量配置

### 3.1 创建 .env.production

```bash
cd deploy
cp .env.production.example .env.production
vim .env.production
```

### 3.2 必填变量

| 变量名 | 生成方法 | 说明 |
|--------|----------|------|
| `YULEOSH_JWT_SECRET` | `openssl rand -hex 32` | JWT 签名密钥 |
| `YULEOSH_DB_PASSWORD` | `openssl rand -hex 16` | PostgreSQL 密码 |
| `YULEOSH_BASE_URL` | 如 `https://yuleosh.io` | 对外访问地址 |
| `LLM_API_KEY` | 从 LLM 提供商获取 | LLM API 密钥 |

### 3.3 推荐变量

| 变量名 | 说明 |
|--------|------|
| `YULEOSH_LOG_LEVEL` | `info` / `debug` / `warning` |
| `CI_STRICT` | `true` 启用严格 CI 检查 |
| `YULEOSH_RATE_LIMIT` | API 速率限制（默认 100 req/min） |

### 3.4 安全注意事项

- **绝不提交** `.env.production` 到版本控制（已在 `.gitignore` 中）
- 每个部署环境使用不同的密钥
- 生产环境禁用 `YULEOSH_DEMO_ENABLED=true`
- JWT 密钥 ≥ 32 字节随机 hex 字符串

---

## 4. 启动服务

### 4.1 标准部署（Nginx + Certbot）

```bash
cd deploy
docker compose -f docker-compose.yml --env-file .env.production up -d

# 查看启动日志
docker compose -f docker-compose.yml logs -f
```

### 4.2 含前端和监控栈的完整部署

```bash
# 从项目根目录使用 docker-compose.prod.yml
cd ..
docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml \
  --env-file deploy/.env.production up -d
```

### 4.3 健康检查验证

```bash
# 后端健康检查
curl https://yuleosh.io/api/health
# 预期: {"status":"ok","version":"2.1.0","db":"connected","uptime":12345}

# 前端（如有）
curl -I https://yuleosh.io
# 预期: HTTP/2 200
```

### 4.4 查看各服务状态

```bash
docker compose -f deploy/docker-compose.yml ps

# 各个服务的日志
docker compose -f deploy/docker-compose.yml logs -f backend
docker compose -f deploy/docker-compose.yml logs -f nginx
docker compose -f deploy/docker-compose.yml logs -f db
```

---

## 5. Stripe 生产 Keys 接入

### 5.1 获取密钥

1. 登录 [Stripe Dashboard](https://dashboard.stripe.com/apikeys)
2. 切换到 **Live mode**（右上角开关）
3. 复制 **Secret key**（以 `sk_live_` 开头）
4. 复制 **Publishable key**（以 `pk_live_` 开头）

### 5.2 配置 Stripe

在 `.env.production` 中设置：

```bash
STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxxxxxxxxxx
STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxx
```

### 5.3 创建产品 + 价格

在 Stripe Dashboard 中：

1. **Products → Add Product**
   - 名称：`yuleOSH Pro`
   - 描述：`SaaS Pro — 无限项目 · 完整流水线 · ASPICE 合规`
   - 定价模式：`Recurring → Monthly`
   - 金额：`¥599`（RMB）

2. 记录生成的 **Price ID**（以 `price_` 开头）

3. 在 `src/yuleosh/usage/metering.py` 中设置：

```python
"pro": {
    ...
    "stripe_price_id": "price_xxxxxxxxxxxxx",  # ← 替换为实际 Price ID
}
```

### 5.4 配置 Webhook Endpoint

1. Stripe Dashboard → **Developers → Webhooks → Add endpoint**

   - **Endpoint URL**: `https://yuleosh.io/api/v1/subscription/webhook`
   - **Events to send**: 选择以下事件：
     - `checkout.session.completed`
     - `customer.subscription.updated`
     - `customer.subscription.deleted`
   - **Signing secret**: 复制并设置到 `STRIPE_WEBHOOK_SECRET`

2. 验证 webhook：

```bash
curl -X POST https://yuleosh.io/api/v1/subscription/webhook \
  -H "Stripe-Signature: whsec_xxx" \
  -H "Content-Type: application/json" \
  -d '{"type":"checkout.session.completed","data":{"object":{"metadata":{"org_id":"1","tier":"pro"},"subscription":"sub_xxx","customer":"cus_xxx"}}}'
```

### 5.5 测试支付流程

Stripe 提供测试卡号用于 sandbox 测试：

| 卡号 | 场景 |
|------|------|
| `4242 4242 4242 4242` | 成功支付 |
| `4000 0000 0000 0002` | 被拒（card_declined） |
| `4000 0025 0000 3155` | 需 3D 验证 |

---

## 6. 生产安全清单

### 6.1 启动前检查清单

- [ ] DNS A 记录已配置并解析正常
- [ ] 端口 80/443 已在防火墙开放
- [ ] SSL 证书已颁发（可通过浏览器验证）
- [ ] `YULEOSH_JWT_SECRET` 已设置为强随机字符串（≥32 字节）
- [ ] `YULEOSH_DB_PASSWORD` 已设置强密码
- [ ] `.env.production` 已创建且不在版本控制中
- [ ] Stripe 生产密钥已配置
- [ ] Stripe Price ID 已在 `metering.py` 中设置
- [ ] Stripe Webhook Endpoint 已在 Dashboard 中创建
- [ ] Nginx `server_name` 已修改为实际域名
- [ ] Nginx SSL 证书路径正确
- [ ] Docker 日志轮转已设置（默认 10MB × 3）
- [ ] 定时数据库备份已配置（见第 7 节）
- [ ] `CI_STRICT=true` 确保严格模式
- [ ] 禁用 demo 模式：`YULEOSH_DEMO_ENABLED=false`

### 6.2 持续安全维护

- [ ] 每月更新依赖（`pip list --outdated`，`npm outdated`）
- [ ] 每季度更新 SSL 证书（Let's Encrypt 自动续签）
- [ ] 每周检查日志：`docker compose logs --tail=200`
- [ ] 监控 Stripe 支付异常通知
- [ ] 定期审查数据库备份完整性

---

## 7. 维护操作

### 7.1 更新版本

```bash
cd /path/to/yuleOSH
git pull
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
```

### 7.2 备份数据库

**PostgreSQL：**

```bash
# 手动备份
docker compose -f deploy/docker-compose.yml exec db \
  pg_dump -U yuleosh yuleosh > backup_$(date +%Y%m%d_%H%M%S).sql

# 定时备份（crontab 示例，每天凌晨 3 点）
0 3 * * * cd /path/to/yuleOSH && docker compose -f deploy/docker-compose.yml exec -T db pg_dump -U yuleosh yuleosh > backups/db_$(date +\%Y\%m\%d).sql
```

**SQLite（默认）：**

```bash
cp .yuleosh/store.db backup_$(date +%Y%m%d).db
```

### 7.3 扩缩容

```bash
# 增加后端实例（需配合 nginx upstream）
docker compose -f deploy/docker-compose.yml up -d --scale backend=3
```

### 7.4 重置管理员密码

```bash
docker compose -f deploy/docker-compose.yml exec db psql -U yuleosh -d yuleosh
UPDATE users SET password_hash = '<new-bcrypt-hash>' WHERE email = 'admin@example.com';
```

### 7.5 查看并分析日志

```bash
# 实时日志
docker compose -f deploy/docker-compose.yml logs -f --tail=100

# 按服务过滤
docker compose logs backend | grep -i error

# 结构化日志（JSON 格式）分析
docker compose logs backend | jq 'select(.level == "ERROR")'
```

---

## 8. 故障排除

### 8.1 启动失败

| 症状 | 排查步骤 |
|:-----|:---------|
| `Connection refused` | PostgreSQL 未就绪：`docker compose logs db` |
| `certbot` 证书申请失败 | 检查 DNS 解析和端口 80 是否开放 |
| Nginx 502 Bad Gateway | `docker compose logs backend` 检查后端是否启动 |
| Stripe webhook 400 | 确认 `STRIPE_WEBHOOK_SECRET` 与 Dashboard 一致 |

### 8.2 常见错误解决

**"JWT secret not configured"**

```bash
echo "YULEOSH_JWT_SECRET=$(openssl rand -hex 32)" >> deploy/.env.production
```

**"Stripe not configured"**

```bash
echo "STRIPE_SECRET_KEY=sk_live_..." >> deploy/.env.production
echo "STRIPE_WEBHOOK_SECRET=whsec_..." >> deploy/.env.production
```

**"Database connection failed"**

```bash
# 检查 PostgreSQL 连接
docker compose exec db pg_isready -U yuleosh
# 确认环境变量正确
docker compose exec backend env | grep YULEOSH_DB_URL
```

**"504 Gateway Timeout"**

Pipeline 运行可能耗时较长，调整 nginx `proxy_read_timeout`：

```nginx
location / {
    proxy_read_timeout 300s;  # 5 分钟
}
```

---

## 9. 参考

- [Docker Compose 文档](https://docs.docker.com/compose/)
- [Let's Encrypt 文档](https://letsencrypt.org/docs/)
- [Stripe Webhooks](https://stripe.com/docs/webhooks)
- [Nginx SSL 配置](https://nginx.org/en/docs/http/configuring_https_servers.html)
- [Caddy 自动 HTTPS](https://caddyserver.com/docs/automatic-https)
- [yuleOSH GitHub](https://github.com/frisky1985/yuleOSH)

---

## 附录 A：快速命令速查

```bash
# 完整启动（推荐）
cd deploy && docker compose -f docker-compose.yml --env-file .env.production up -d

# 停止所有服务
docker compose -f docker-compose.yml down

# 重建并重启
docker compose -f docker-compose.yml up -d --build

# 查看所有服务日志
docker compose -f docker-compose.yml logs -f

# 只查看后端日志
docker compose -f docker-compose.yml logs -f backend

# 备份数据库
docker compose -f docker-compose.yml exec db pg_dump -U yuleosh yuleosh > backup.sql

# 健康检查
curl https://yuleosh.io/api/health
```
