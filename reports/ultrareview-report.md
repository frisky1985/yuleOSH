# UltraReview — yuleOSH 全量代码深度审查报告

**审查日期**: 2026-07-10  
**审查范围**: `src/yuleosh/` (Python 后端), `frontend/` (Next.js), `desktop/` (Electron), `tests/`  
**审查版本**: v0.8.0+

---

## 审查概要

| 模块 | 文件数 | 行数 | 安全问题 | 代码质量 | 架构问题 |
|------|--------|------|----------|----------|----------|
| src/yuleosh/ (Python 后端) | 40+ | ~12K | 8 | 12 | 5 |
| frontend/ (Next.js) | 15+ | ~3K | 1 | 3 | 1 |
| desktop/ (Electron) | 4 | ~600 | 2 | 2 | 1 |
| tests/ | 20+ | ~3K | 0 | 2 | 0 |

**综合评分**: 6.5/10 — 核心架构合理，但存在部分高危安全遗漏和代码质量问题。

---

## 1. 安全性 (Security)

### P0（阻塞）— 3 项

#### 🔴 S-P0-01: API Router CORS 通配符 `*` + 敏感端点暴露

**文件**: `src/yuleosh/api/router.py` (L78), `src/yuleosh/ui/server.py` (多处)

```python
handler.send_header("Access-Control-Allow-Origin", "*")
```

- **问题**: 所有 API 响应都设置了 `Access-Control-Allow-Origin: *`，意味着任何外部网站都可以在浏览器中通过 `fetch()` 读取 API 响应。
- **影响**: 虽然主要 cookie 授权使用 `HttpOnly; SameSite=Lax` 提供一定保护，但 JWT Bearer token 存在于 `localStorage` 中。如果攻击者通过 XSS 或子域名接管获取 token，则可利用 CORS 通配符直接访问所有 API。
- **修复**: 在非开发环境中应配置白名单域名，或使用 `Vary: Origin` + 请求 Origin 验证。

#### 🔴 S-P0-02: PostgresStore 默认 DSN 硬编码凭据

**文件**: `src/yuleosh/store_pg.py` (L29)

```python
self.dsn = dsn or os.environ.get(
    "YULEOSH_DB_URL",
    "postgresql://yuleosh:yuleosh@localhost:5432/yuleosh"
)
```

- **问题**: 当 `YULEOSH_DB_URL` 环境变量未设置时，使用硬编码的默认凭据 `yuleosh:yuleosh`。
- **影响**: 在生产部署中如果忘记设置环境变量，数据库将以默认弱凭据暴露在 localhost。虽然仅限本地访问，但任何可执行代码的进程都可直接连接。
- **修复**: 移除默认值，或当未设置环境变量时抛出明显错误。

#### 🔴 S-P0-03: API v1 错误处理泄漏堆栈信息到客户端

**文件**: `src/yuleosh/api/router.py` (L59)

```python
except Exception as e:
    import traceback
    traceback.print_exc()
    _respond(handler, *json_error(f"Internal error: {e}", 500))
```

- **问题**: 将原始异常消息 `{e}` 直接返回给客户端。`traceback.print_exc()` 仅打印到 stdout（可能不被日志系统捕获）。
- **影响**: 生产环境中可能泄漏内部路径、SQL 语句、配置片段等敏感信息。
- **修复**: 记录完整 traceback 到结构化日志，只返回通用错误消息。

### P1（重要）— 5 项

#### 🟡 S-P1-01: 双重认证系统并行存在且逻辑边界模糊

**文件**: `src/yuleosh/ui/server.py` (多行), `src/yuleosh/api/auth.py`

- **问题**: 项目中存在两套独立的认证机制：
  1. **Legacy Auth** (`auth.py`): API Key + session cookie，基于 hmac.compare_digest
  2. **Tenant Auth** (`auth_extended.py`): JWT + bcrypt + rate limiting
- `do_GET()` / `do_POST()` 中部分路由走 legacy，部分走 tenant。路由判断链复杂，条件分支多，容易遗漏。某些端点（如 `/api/status`、`/api/evidence`、`/api/reviews`、`/api/ci`）只有 legacy auth 检查，不使用 JWT。
- **修复**: 统一认证中间件，所有请求共用一个认证管线。

#### 🟡 S-P1-02: `read_body()` JSON 解析静默降级

**文件**: `src/yuleosh/api/__init__.py` (L35-45)

```python
try:
    return json.loads(raw)
except (json.JSONDecodeError, UnicodeDecodeError):
    parsed = parse_qs(raw)
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
```

- **问题**: 当 JSON 解析失败时，静默尝试 query-string 格式解析。这可能导致：
  - Content-Type 混淆攻击：发送 `Content-Type: application/json` 但 body 是 `key=value` 格式
  - 隐藏真正的请求格式错误（开发中难以调试）
- **修复**: 应根据 `Content-Type` header 选择解析器，失败时返回 400 错误。

#### 🟡 S-P1-03: PostgresStore 连接非线程安全

**文件**: `src/yuleosh/store_pg.py` (L37-44)

```python
@property
def conn(self):
    if self._conn is None or self._conn.closed:
        self._conn = psycopg2.connect(self.dsn)
        self._conn.autocommit = True
    return self._conn
```

- **问题**: `psycopg2` 连接**不是**线程安全的。`conn` 属性返回同一个连接实例，且没有任何锁保护。当多个线程同时使用 `self.conn.cursor()` 时会产生竞争条件。
- **修复**: 使用 `psycopg2.pool.ThreadedConnectionPool` 或 `psycopg2` 的连接池。

#### 🟡 S-P1-04: JWT_SECRET 默认值进程级随机导致 token 重启即失效

**文件**: `src/yuleosh/ui/auth_extended.py` (L47)

```python
JWT_SECRET = os.environ.get("YULEOSH_JWT_SECRET", secrets.token_urlsafe(32))
```

- **问题**: 当 `YULEOSH_JWT_SECRET` 未设置时，每个进程启动都会生成新的随机密钥。所有已签发的 JWT 在重启后立即失效，所有用户被迫重新登录。
- **影响**: 生产环境重启导致全量用户登出。
- **修复**: 应要求显式配置 `YULEOSH_JWT_SECRET` 环境变量。

#### 🟡 S-P1-05: 桌面端静态文件服务器无路径验证

**文件**: `desktop/main.js` (L183-195)

```javascript
const fullPath = path.join(FRONTEND_OUT_DIR, filePath);
fs.stat(fullPath, (err, stats) => {
```

- **问题**: `filePath` 仅做了 `/yuleOSH/` 前缀剥离，不做路径遍历检测。如果请求 `/yuleOSH/../../../etc/passwd`，`path.join` 可能会解析到 frontend out 目录之外。Node.js 的 `path.join` 会 normalize，但攻击者仍可尝试绕过。
- **影响**: 低风险（仅限本地访问，sandboxed），但应添加路径验证。

### P2（建议）— 3 项

- **S-P2-01**: `handle_signin` 无密码强度验证（最小长度、复杂度）。`auth_extended.py`
- **S-P2-02**: 速率限制器 (`_SIGNIN_RATE_LIMIT`) 是进程级内存 dict，不跨进程共享，多 workers 下可绕过。`auth_extended.py`
- **S-P2-03**: 前端 token 存储在 `localStorage`（`api.ts`），无 `httpOnly` 保护，XSS 可窃取。

---

## 2. 代码质量 (Code Quality)

### P0（阻塞）— 0 项

（无致命代码质量缺陷）

### P1（重要）— 5 项

#### 🔶 CQ-P1-01: `_migrate()` 在 `__new__()` 中执行 — 非预期的 IO 操作

**文件**: `src/yuleosh/store_pg.py` (L33)

```python
def __new__(cls, dsn: Optional[str] = None):
    ...
    instance._migrate()
    ...
```

- **问题**: `__new__` 是 Python 对象创建的最低层级入口，在此执行数据库迁移是反模式。
  - 如果数据库连接失败，非预期的 `psycopg2.OperationalError` 会传播到调用方
  - `__new__` 中的异常会导致整个类的创建失败
  - 迁移应在明确的初始化阶段执行，而非每次单例获取时
- **修复**: 将迁移移到单独的 `init()` 或 `setup()` 方法。

#### 🔶 CQ-P1-02: 向后兼容 `chat_completion()` 重用已消费的 HTTP 请求对象

**文件**: `src/yuleosh/llm/client.py` (L198-231)

```python
req = urllib.request.Request(url, data=payload, ...)
for attempt in range(1, retries + 1):
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ...
```

- **问题**: `Request` 对象在首次 `urlopen` 调用后。Python 文档指出，`Request.data` 是可变的，但 `urlopen` 消费后的 `Request` 不应被重用。更重要的是 `payload` 是创建 `Request` 时传入的 bytes，但对于流式请求体这可能无效。
- **修复**: 每次重试创建新的 `Request` 对象。

#### 🔶 CQ-P1-03: `except Exception: pass` 多处静默吞异常

**文件**: 多处（`llm/client.py` L167, `auth_extended.py`, `notify.py`, `api/preview.py`）

- **影响**: 隐藏了真正的错误原因，使调试变得极其困难。例如：

```python
try:
    CostLogger.log_dict(...)
except Exception as e:
    log.warning("Failed to log LLM call: %s", e)
```

- 这个看起来无害，但**下面**的 failure logging 中：

```python
except Exception:
    pass  # ← 完全静默
```

- **修复**: 至少记录警告级别日志，不要全静默。

#### 🔶 CQ-P1-04: `api/preview.py` 使用不受保护的内存状态

**文件**: `src/yuleosh/api/preview.py` (L53-56)

```python
_assessment_store: dict[str, dict] = {}
```

- **问题**: preview 模块使用进程级内存 dict 存储评估状态，且没有任何锁保护。当并发请求到达时可能出现状态覆盖、读取到半初始化状态等数据竞争。
- **修复**: 使用 `threading.Lock` 保护，或使用 Redis/数据库存储。

#### 🔶 CQ-P1-05: 迁移版本常量但无自动执行升级

**文件**: `src/yuleosh/store_pg.py` (L90)

```python
_MIGRATION_VERSION = 7
```

- 定义了版本号，但没有实际的版本迁移逻辑——当前 `_migrate()` 每次都从头创建所有表。这意味着已有数据的数据库升级时不安全（`CREATE TABLE IF NOT EXISTS` 安全，但没有 schema 演进）。
- **修复**: 实现从版本 `_MIGRATION_VERSION` 向前迁移。

### P2（建议）— 6 项

- **CQ-P2-01**: 混合使用 `Optional[T]`（Legacy）和 `T | None`（Modern）类型注解
- **CQ-P2-02**: `sys.path.insert` 在模块体中使用（`server.py`, `__init__.py`, `stages.py`）— 应使用可安装包 `pip install -e .`
- **CQ-P2-03**: 未使用的 import 多处（如 `store.py`, `ui/server.py`）
- **CQ-P2-04**: 部分函数过长（`ui/server.py` 中的 `do_GET()` ~150行，`spec/validate.py` 中的 `parse_spec()` ~200行）
- **CQ-P2-05**: 测试覆盖率门限 (`--cov-fail-under=50`) 偏低，应逐步提升至 70+
- **CQ-P2-06**: `docker-compose.yml` 未审查（项目根目录）

---

## 3. 架构 (Architecture)

### P1（重要）— 3 项

#### 🔷 AR-P1-01: 遗留 API 后缀和 tenant API 严重碎片化

**文件**: `src/yuleosh/ui/server.py` (do_GET 中约 50 个 if/elif)

- 服务器有四个不同的 API 区域：
  - `/api/v1/*` — 新的模块化 API 路由器
  - `/api/*`（health, status, evidence, reviews, ci）— 旧的裸露端点
  - `/api/auth/*` — tenant auth 端点
  - `/api/org/*`, `/api/project/*` — tenant 资源端点

每个区域的认证检查逻辑不同，请求处理方式不同，这种碎片化导致认证绕过和安全边界模糊的高风险。

#### 🔷 AR-P1-02: `Store` vs `PostgresStore` 双实现无统一接口

**文件**: `src/yuleosh/store.py`, `src/yuleosh/store_pg.py`

- `store.py` 实现了 SQLite 版本，`store_pg.py` 实现了 PostgreSQL 版本。两者之间有显著的 API 差异（PostgresStore 有 `create_organization/` `create_user/` `list_organizations/` 等方法，Store 没有）。
- **影响**: 用户项目使用了 postgres URL 时，`api/project.py` 等方法中 `from yuleosh.store import Store` 导入的是 SQLite 版本，不是 PostgresStore。导致多租户功能未登录时可能使用不同的后端。
- **修复**: 引入抽象基类 `AbstractStore`，让 `Store` 根据 URL 返回适当实现。

#### 🔷 AR-P1-03: Electron 前端加载不等待后端就绪

**文件**: `desktop/main.js` (L332-335)

```javascript
await createWindow();  // 立即加载前端页面
startBackend();        // 异步启动后端
```

- **影响**: 网页加载后可能立即显示 "Backend not reachable" 错误，直到健康检查完成（最长 15s）。用户体验差。
- **修复**: 使用加载页面等待后端 ready，或内置后端状态轮询组件。

### P2（建议）— 3 项

- **AR-P2-01**: API v1 路由器无条件加载所有路由模块，包括可能不需要的模块。
- **AR-P2-02**: `chat_completion()` 在 `client.py` 中重复 `urllib` 逻辑 — 应由各 provider 模块统一处理。
- **AR-P2-03**: 项目根依赖 `setup.py` 与 `pyproject.toml` 共存，推荐统一为 `pyproject.toml`。

---

## 4. 合规与 spec 对齐 (Compliance / Spec Alignment)

### P1（重要）— 2 项

#### 🟣 CP-P1-01: API v1 路由无审计日志集成

**文件**: `src/yuleosh/api/router.py` — `dispatch()` 函数

- 当前 `_audit_log()` 仅在 `ui/server.py` 中的 `OSHHandler` 方法中调用（legacy 路径）。新的 API v1 路由 `dispatch()` 完全不记录审计日志。
- **影响**: 所有通过 `/api/v1/*` 的请求不可审计，违反 ASPICE SUP.9 问题管理（SEC-04 日志完整性）。

#### 🟣 CP-P1-02: Legacy auth 响应非一致错误格式

**对比**: `src/yuleosh/api/__init__.py` 使用 `{ok, data}` / `{ok, error}`  
**对比**: `src/yuleosh/ui/server.py` 中使用 `handle_auth_check` 返回 `{error, message}`

- 当 API v1 标准是 `{ok: false, error: "..."}`，但 `do_GET` 中的认证拒绝返回的是 `{error: "unauthorized", message: "..."}`（字段不同）。
- **修复**: 统一错误响应格式。

### P2（建议）— 2 项

- **CP-P2-01**: `spec/validate.py` 中的 `PRICING_TABLE` 和 `TASK_BUDGETS` 在 `base.py` 和 `client.py` 中有重叠定义 — 应只有一个来源。
- **CP-P2-02**: 测试文件命名不一致（`test_*.py` 和 `*_test.py` 混用），影响测试发现。

---

## 5. 按模块汇总

### 5.1 `src/yuleosh/api/` — REST API 路由模块

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| CORS 通配符 | P0 | 所有端点 `Access-Control-Allow-Origin: *` |
| 错误堆栈泄漏 | P0 | `Internal error: {e}` 暴露细节到客户端 |
| read_body 静默降级 | P1 | JSON 解析失败时静默用 query-string 代替 |
| 无审计日志 | P1 | `/api/v1/*` 不记录审计日志 |
| 错误格式不统一 | P1 | `{ok, error}` vs `{error, message}` |

### 5.2 `src/yuleosh/store_pg.py` — PostgreSQL 存储

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| 默认硬编码凭据 | P0 | `yuleosh:yuleosh@localhost` |
| 非线程安全连接 | P1 | 单连接被多线程共享 |
| __new__ 执行迁移 | P1 | 创建阶段执行数据库 IO |
| 无 schema 演进 | P1 | CREATE TABLE IF NOT EXISTS 不安全于升级 |

### 5.3 `src/yuleosh/llm/` — LLM 客户端

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| Request 对象重用 | P1 | 重试中共享已消费的 HTTP Request |
| 多个 API key 环境变量 | P1 | 多个 env 源，解析逻辑隐式 |
| `except Exception: pass` | P1 | failure 日志完全静默 |

### 5.4 `src/yuleosh/ui/auth_extended.py` — 多租户认证

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| JWT 密钥默认随机 | P1 | 重启后所有 token 失效 |
| 无密码策略 | P2 | 无最小长度/复杂度验证 |
| 速率限制器仅内存 | P2 | 不跨进程 |

### 5.5 `src/yuleosh/api/preview.py` — AI Preview

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| 内存状态无锁 | P1 | 并发安全 |
| git URL 白名单仅 3 个主机 | P2 | 扩展性受限 |

### 5.6 `frontend/` — Next.js 前端

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| Token 存 localStorage | P2 | 无 httpOnly，XSS 可窃取 |
| 无 CSP header | P2 | 静态导出模式缺少内容安全策略 |
| `next.config.ts` 硬编码路径 | P2 | `root` 指向本地机器路径 |

### 5.7 `desktop/` — Electron 桌面版

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| 静态文件遍历风险 | P1 | 无 path traversal 确认 |
| 前端加载不等待后端 | P1 | 先加载 UI 再异步启动后端 |
| `sandbox: false` | P1 | 渲染进程可以访问 Node.js API（经 preload 桥接） |

### 5.8 `tests/` — 测试

| 问题 | 严重级别 | 说明 |
|------|----------|------|
| 覆盖率目标低 | P2 | 仅 50% fail-under |
| 测试文件命名不一致 | P2 | `test_*` vs `*_test` |

---

## 6. 综合建议 (Top 5 Actions)

### 行动 1: 统一认证和 CORS（P0 修复，预估 2天）
- 废除双认证系统，统一为 JWT + bcrypt
- 在 router 和 server 中添加 CORS 域名白名单
- 为所有 API 响应（包括 /api/v1/*）添加标准审计日志

### 行动 2: 数据库连接安全管理（P0-P1，预估 1天）
- 移除 store_pg.py 中的硬编码默认 DSN
- 使用 `psycopg2.pool` 线程安全连接池
- 将 `_migrate()` 移出 `__new__()`

### 行动 3: 统一 Store 接口（P1，预估 3天）
- 创建 `AbstractStore` 抽象基类
- `Store()` 根据 URL 自动返回 SQLite 或 Postgres 实现
- 解决 `project.py` 等重度使用 SQLite Store 的遗留问题

### 行动 4: 安全加固 API 错误处理（P0-P1，预估 1天）
- 所有异常处理改为结构化日志 + 通用错误消息
- 移除 `except Exception: pass`
- 统一错误响应格式

### 行动 5: 架构优化（P1，预估 3天）
- 解耦 `ui/server.py` 中的 50+ if/elif 路由
- `api/v1` router 添加审计日志
- Electron 桌面加载流程改为"等待后端就绪再加载 UI"

---

## 7. 技术债务总览

| 类别 | P0 | P1 | P2 | 总计 |
|------|----|----|----|------|
| 安全性 | 3 | 5 | 3 | 11 |
| 代码质量 | 0 | 5 | 6 | 11 |
| 架构 | 0 | 3 | 3 | 6 |
| 合规 | 0 | 2 | 2 | 4 |
| **总计** | **3** | **15** | **14** | **32** |

---

*报告结束 — UltraReview v1.0*
