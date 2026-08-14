# yuleOSH Docker Compose 部署说明

> 适用于「收到 Demo 包后快速启动」的场景。

## 方式 1: Docker Compose 一键启动（推荐）

### 前置条件

- Docker ≥ 24
- Docker Compose ≥ 2.24

### 启动

```bash
# 从项目根目录
cd yuleosh

# 本地体验模式（无认证）
docker compose up -d

# 浏览器访问
open http://localhost:8080
```

### 配置说明

`docker-compose.yml`（项目根目录）已预设本地体验模式：

| 环境变量 | 值 | 说明 |
|----------|-----|------|
| `OSH_PORT` | 8080 | 服务端口 |
| `YULEOSH_AUTH_DISABLED` | true | 跳过登录 |
| `YULEOSH_STORE_DIR` | /data | 数据持久化目录 |
| `YULEOSH_LOG_LEVEL` | INFO | 日志级别 |

数据卷 `yuleosh-data` 挂载到容器 `/data`，重启后数据不丢失。

## 方式 2: 生产部署

参见 `deploy/docker-compose.yml` + `deploy/README.md`。

包含 PostgreSQL + Nginx + Certbot 全套生产组件：

```bash
cd yuleosh
cp deploy/.env.example .env
# 编辑 .env 配置
docker compose -f deploy/docker-compose.yml up -d
```

## 方式 3: 裸机部署（无 Docker）

```bash
# 1. 安装依赖
pip install -e .

# 2. 启动 Dashboard 服务器
python3 src/ui/server.py &
# 或
yuleosh ui &

# 3. (可选) 安装 pre-commit hook
yuleosh hook install

# 4. 使用 CLI
yuleosh --help
```

## 系统依赖检查

```bash
# Python
python3 --version          # ≥ 3.10

# 静态分析（MISRA 必需）
cppcheck --version         # ≥ 2.14

# 代码格式化（可选）
clang-format --version

# 单元测试框架
pytest --version
```

## 验证部署

```bash
# 1. 检查服务
curl http://localhost:8080/api/health

# 2. 初始化项目
yuleosh init demo-test

# 3. 运行 MISRA 检查
cd demo-test
echo "int x = 0;" > src/test.c
yuleosh ci run 1

# 4. 检查知识库
yuleosh kb list
```
