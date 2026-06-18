# SWE.6 确认测试规范

> **ASPICE 4.0 关联**: SWE.6 — 软件合格性测试 (Software Qualification Testing)  
> **BP 关联**: SWE.6-BP1: 制定确认测试规范  
> **文档版本**: v1.0.0 | **状态**: 初版  
> **维护人**: 小马 🐴 (质量架构师)

---

## 1. 确认测试范围定义

### 1.1 定义

确认测试 (Confirmation Test) 验证 yuleOSH 系统在**目标运行环境**下是否满足**软件需求规范 (RS-001 ~ RS-014)** 中定义的 SHALL 语句。与单元测试 (SWE.3)、集成测试 (SWE.5) 不同，确认测试聚焦于：

- **端到端 (E2E)** 业务流程验证
- **发布门禁** 条件判定
- **环境兼容性** 确认
- **非功能性需求** 在真实或类生产环境中的验证

### 1.2 范围

| 覆盖项 | 说明 | 验证级别 |
|:-------|:-----|:--------:|
| 注册 → 登录 → Trial → Pro 升级 → 降级 | 完整 SaaS 用户生命周期 (RS-014) | E2E |
| Pipeline 从提交到证据包生成的完整执行 | Agent 驱动开发流水线 (RS-001) | E2E |
| Web UI 核心页面可访问性与响应式 | 多端接入 (RS-006) | E2E |
| SaaS Demo 与 AI Preview 体验 | Demo (RS-012) + Preview (RS-013) | E2E |
| Stripe 支付回调与订阅状态同步 | 支付集成 (RS-014.3) | E2E |
| SIL 测试在 CI 中的门禁效果 | SIL 仿真 (RS-008) | 系统验证 |
| HIL 测试在 CI L2.5 中的执行 | HIL 硬件测试 (RS-009) | 系统验证 |
| 模板初始化 CLI 命令 | 模板市场 (RS-011) | E2E |
| CI 门禁 (覆盖率和 RTM) 正确触发 | CI/CD 门禁 (RS-004) | 系统验证 |

### 1.3 排除项

- **单元测试**: 由 SWE.3 覆盖，不在确认测试范围
- **集成测试**: 由 SWE.5 覆盖，不在确认测试范围
- **第三方依赖功能**: 如 Stripe Dashboard、GitHub Actions、AWS S3 原生管理界面
- **非功能性负载测试**: 由独立性能测试覆盖（`tests/test_perf_baseline.py`，ASPICE SWE.4-BP4）

---

## 2. 测试环境规范

### 2.1 环境层级

| 环境 | 用途 | 数据 | 网络 | 外部服务 |
|:----|:-----|:----|:----|:---------|
| **开发 (Dev)** | 开发者本地验证 | Mock 数据 / SQLite | 本地 | Stripe Test Keys |
| **预发布 (Staging)** | 发布候选验证 | 合成数据集 / 脱敏 | 内网 | Stripe Test, SendGrid Test |
| **生产 (Production)** | 上线后监控与 Smoke | 真实用户数据 | 公网 | Stripe Live, SendGrid Live |

### 2.2 环境配置要求

#### Dev 环境
- Python 3.11+
- Node.js 20+
- SQLite 或 PostgreSQL (本地)
- Stripe CLI (webhook 本地转发生成)
- QEMU 8.x (SIL 测试)
- Docker (可选，容器化运行)

#### Staging 环境
- 与生产环境相同的 PostgreSQL 版本（推荐 16+）
- Stripe Test Mode keys (`sk_test_*`)
- 与生产一致的 Docker 镜像版本
- 与生产相同的 DNS 和 SSL 配置
- 独立的数据库实例（隔离开发数据）
- CI L3 运行环境与 Staging 一致

#### 生产环境
- PostgreSQL 16+ 生产实例（HA 配置）
- Stripe Production keys (`sk_live_*`)
- HTTPS 证书 (Let's Encrypt 自动续期)
- Redis 缓存层
- 对象存储 (OSS/S3) 用于证据包归档
- 监控 + 日志聚合 (Grafana + Loki)
- 灾备与备份策略

### 2.3 环境间差异清单

| 差异项 | Dev | Staging | Production |
|:-------|:---:|:-------:|:----------:|
| Stripe Mode | Test | Test | Live |
| 邮件发送 | Console 输出 | SendGrid Test | SendGrid Live |
| 数据库 | SQLite/本地 PG | 独立 PG | 生产 PG (HA) |
| 数据 | Mock | 合成数据 | 真实数据 |
| 监控 | ❌ | ✅ | ✅ |
| 备份 | ❌ | 每日全量 | 每日 + WAL 归档 |

---

## 3. 测试用例清单

### TC-CONF-001: 用户注册 → 登录 → Trial 项目创建 (全链路)

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-014 / SWR-014.1 |
| **优先级** | P0 |
| **环境** | Dev → Staging |
| **类型** | E2E |
| **自动化** | ✅ Playwright + pytest |

**前置条件**:
- 数据库为空（无用户）
- 注册接口可访问

**测试步骤**:
1. 发送注册请求 (POST /api/auth/register) 携带 name="Test User", email="test@example.com", password="ValidP@ss1"
2. 验证 HTTP 201 响应包含 JWT token
3. 验证数据库新增 user 记录，status="active"
4. 验证数据库新增 project 记录，plan="trial"
5. 使用 JWT token 调用 GET /api/projects 验证返回 Trial 项目
6. 登出后使用同一凭据登录，验证成功

**通过标准**:
- [ ] 注册返回 JWT token（非空字符串，有效 JWT 格式）
- [ ] 数据库中 users 表包含新用户
- [ ] 数据库中 projects 表包含自动创建的 Trial 项目
- [ ] JWT 可成功认证后续 API 请求

**失败标准**:
- [ ] 注册返回非 201 状态码
- [ ] 数据库无 user 记录或无 project 记录
- [ ] JWT 无效或无法通过认证

---

### TC-CONF-002: Trial → Pro 升级 (Stripe Checkout 全流程)

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-014 / SWR-014.2 / SWR-014.3 |
| **优先级** | P0 |
| **环境** | Dev (Stripe Test) |
| **类型** | E2E |
| **自动化** | ✅ pytest + Stripe CLI (test clock) |

**前置条件**:
- 用户已注册且为 Trial 状态
- Stripe Test Mode 已配置
- Stripe CLI 可用 (用于触发 webhook)

**测试步骤**:
1. 登录 Trial 用户
2. 调用 GET /api/subscription 验证当前 plan="trial"
3. 调用 POST /api/subscription/upgrade 触发升级
4. 验证响应返回 Stripe Checkout URL (302 或 JSON 中包含 url)
5. 使用 Stripe Test Card (`4242 4242 4242 4242`) 完成 Checkout
6. 模拟 Stripe webhook: `stripe trigger checkout.session.completed`
7. 调用 GET /api/subscription 验证 plan="pro"
8. 验证项目中 pro 功能已解锁

**通过标准**:
- [ ] Trial 用户可发起升级
- [ ] Stripe Checkout URL 有效且可访问
- [ ] Webhook 处理后订阅状态更新为 pro
- [ ] Pro 功能可访问

**失败标准**:
- [ ] 升级请求返回错误
- [ ] Checkout URL 无效
- [ ] 支付后订阅状态未更新
- [ ] Pro 功能在升级后仍被限制

---

### TC-CONF-003: Pro → 降级/取消订阅

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-014 / SWR-014.2 (SHOULD) |
| **优先级** | P1 |
| **环境** | Dev (Stripe Test) |
| **类型** | E2E |
| **自动化** | ✅ pytest + Stripe CLI |

**前置条件**:
- 用户为 Pro 订阅状态
- Stripe Test subscription 已创建

**测试步骤**:
1. 登录 Pro 用户
2. 调用 POST /api/subscription/cancel
3. 验证响应明确延期生效日期或立即降级
4. 模拟 Stripe webhook `customer.subscription.updated` (canceled)
5. 验证数据库 subscription status = "canceled" 或 "past_due"
6. 验证 Pro 功能被限制为 Free 层级
7. 验证 Trial 项目仍然可访问（只读）

**通过标准**:
- [ ] 取消请求被接受
- [ ] 订阅标记为已取消或待取消
- [ ] 降级后功能限制正确
- [ ] 用户数据不丢失

---

### TC-CONF-004: Demo Pipeline 全流程 (无需登录)

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-012 / SWR-012.1 / SWR-012.2 |
| **优先级** | P0 |
| **环境** | Dev → Staging |
| **类型** | E2E |
| **自动化** | ✅ Playwright + pytest |

**前置条件**:
- 服务已启动
- `YULEOSH_DEMO_ENABLED` 为 true (默认)

**测试步骤**:
1. 访问首页，验证 "Try Demo" 按钮存在且可点击
2. 点击按钮，验证跳转到 `/demo`
3. 验证 GET /api/demo/pipeline 返回 JSON 数据
4. 验证 demo 页面显示 10 个 pipeline 步骤动画
5. 验证所有步骤完成后显示 final report + download + sign-up CTA
6. 验证 sign-up CTA 链接到注册页面

**通过标准**:
- [ ] "Try Demo" 按钮存在于首页 hero 区域
- [ ] `/demo` 无需认证可访问
- [ ] 10 个步骤按顺序完成动画
- [ ] 最终结果显示报告、下载、注册 CTA

---

### TC-CONF-005: AI Preview Assessment 全流程

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-013 / SWR-013.1 / SWR-013.2 / SWR-013.3 |
| **优先级** | P0 |
| **环境** | Dev |
| **类型** | E2E |
| **自动化** | ✅ pytest |

**前置条件**:
- 服务已启动
- 测试用 ZIP 临时项目文件可用

**测试步骤**:
1. POST ZIP 文件到 /api/preview/assess，验证 202 和 preview_id
2. 每 5 秒轮询 GET /api/preview/assess/{preview_id} 直到完成
3. 验证最终报告包含 coverage prediction、compliance risk、pipeline config
4. 验证未认证 IP 第 4 次请求返回 429

**通过标准**:
- [ ] ZIP 上传返回 202
- [ ] 轮询最终返回 completed 状态
- [ ] 报告包含所有三个分析维度
- [ ] 限流正确生效

---

### TC-CONF-006: Stripe Webhook 回调与状态同步

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-014 / SWR-014.3 |
| **优先级** | P0 |
| **环境** | Dev (Stripe Test) |
| **类型** | E2E |
| **自动化** | ✅ pytest + Stripe CLI |

**前置条件**:
- Stripe Test 模式已配置
- Webhook 端点已配置并验证签名有效

**测试步骤**:
1. 使用 Stripe CLI 发送 `checkout.session.completed` 事件（包含 test checkout session）
2. 验证服务器返回 HTTP 200
3. 验证数据库订阅状态更新为 pro
4. 发送无效签名的事件，验证返回 401 且数据库不变
5. 发送 `customer.subscription.deleted` 事件
6. 验证数据库状态更新

**通过标准**:
- [ ] 有效事件被处理，状态同步成功
- [ ] 无效事件被拒绝（401），状态不变
- [ ] 订阅删除事件正确处理

---

### TC-CONF-007: CLI 模板初始化

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-011 / SWR-011.2 |
| **优先级** | P1 |
| **环境** | Dev |
| **类型** | CLI E2E |
| **自动化** | ✅ pytest (subprocess) |

**前置条件**:
- yuleosh 已安装或可从当前目录运行

**测试步骤**:
1. 运行 `yuleosh template list`，验证输出包含至少 5 个模板
2. 运行 `yuleosh project init --template zephyr-rtos /tmp/test-proj`
3. 验证生成的文件结构包含: docs/spec.md, pipeline/config.yaml, src/, yuleosh.yaml
4. 运行 `yuleosh project init` (无参数)，验证进入交互模式

**通过标准**:
- [ ] template list 返回 ≥ 5 个模板
- [ ] 模板初始化创建正确的骨架
- [ ] 交互模式正常

---

### TC-CONF-008: CI 门禁正确触发 (覆盖率和 RTM)

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-004 / SWR-003.2 / SWR-010.2 |
| **优先级** | P0 |
| **环境** | Dev → CI |
| **类型** | 系统验证 |
| **自动化** | ✅ pytest (集成) |

**前置条件**:
- CI 配置就绪
- 已知覆盖率不足的代码更改可用

**测试步骤**:
1. 提交一个覆盖率降到 75% 以下的 PR
2. 验证 CI L1 阶段 coverage guardian 正确阻塞
3. 提交一个新增 SHALL 语句但无测试的 PR
4. 验证 CI RTM 门禁标记未覆盖 SHALL
5. 提交一个满足所有门禁的 PR，验证全部通过

**通过标准**:
- [ ] 覆盖率不足时 L1 正确阻塞
- [ ] RTM 门禁正确检测未覆盖 SHALL
- [ ] 满足条件时 CI 全部通过

---

### TC-CONF-009: SIL 仿真测试在 CI 中的门禁

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-008 / SWR-008.3 |
| **优先级** | P0 |
| **环境** | Dev → CI |
| **类型** | 系统验证 |
| **自动化** | ✅ pytest |

**前置条件**:
- QEMU 可用
- 编译好的 .elf 固件可用

**测试步骤**:
1. 提交一个 SIL 测试全部通过的 PR
2. 验证 CI L2 全部 PASS
3. 提交一个 SIL 测试 FAIL 的 PR (修改固件使某串口断言失败)
4. 验证 CI L2 被 SIL 测试阻塞
5. 验证 evidence pack 中包含 sil-test-report.json

**通过标准**:
- [ ] SIL 测试全部通过时 CI L2 PASS
- [ ] SIL 测试失败时 CI L2 FAIL (阻塞)
- [ ] evidence pack 包含 report

---

### TC-CONF-010: Web UI 核心页面可访问性

| 属性 | 值 |
|:----|:---|
| **需求追溯** | RS-006 |
| **优先级** | P1 |
| **环境** | Dev → Staging |
| **类型** | E2E |
| **自动化** | ✅ Playwright |

**前置条件**:
- 前端服务已启动

**测试步骤**:
1. 访问首页 `/`，验证响应式布局
2. 访问 `/pricing`，验证定价表
3. 访问 `/docs/faq`，验证 FAQ 可访问
4. 访问 `/docs/user-guide`，验证用户指南
5. 访问 `/login`，验证登录页
6. 访问 `/register`，验证注册页
7. 访问 `/dashboard` (未登录)，验证跳转到登录页

**通过标准**:
- [ ] 所有公共页面 HTTP 200
- [ ] 登录保护页面正确重定向

---

## 4. 通过/失败标准

### 4.1 单用例判定

每个测试用例的通过/失败判定按以下规则执行：

```
PASS = 所有 [ ] 通过标准标记为 ✅
FAIL = 任一 [ ] 通过标准标记为 ❌
BLOCKED = 前置条件未满足或环境不可用
SKIPPED = 该用例不适用于本次发布
```

### 4.2 发布门禁等级

| 等级 | 阈值 | 判定 |
|:----|:----|:----|
| 🟢 **Go** | 所有 P0 E2E 通过 (TC-CONF-001, 002, 004, 005, 006, 008) | 可发布 |
| 🟡 **Conditional Go** | P0 E2E 通过, P1 失败 ≤ 2 项 | 有条件发布，需记录待办 |
| 🔴 **No-Go** | 任一 P0 E2E 失败 | 阻塞发布，需修复后重审 |

### 4.3 数据一致性检查

确认测试执行后，需验证以下数据一致性：

- [ ] 用户数量 = 注册数
- [ ] 订阅总数 = Pro 用户数
- [ ] 项目总数 ≥ 用户数 (每个用户至少 1 个 Trial 项目)
- [ ] 不存在幽灵项目 (无归属用户的 project 记录)

---

## 5. 发布门禁条件

### 5.1 硬性门禁 (Blockers)

以下条件 ALL 满足方可发布：

| # | 门禁条件 | 关联 TC | 验证方式 |
|:-|:---------|:-------:|:--------|
| G-01 | 注册 → Trial 创建全链路通过 | TC-CONF-001 | 自动化 E2E |
| G-02 | Stripe 支付 → 订阅状态同步通过 | TC-CONF-002, 006 | 自动化 E2E |
| G-03 | Demo Pipeline 体验正常 | TC-CONF-004 | 自动化 E2E |
| G-04 | AI Preview 正常返回分析报告 | TC-CONF-005 | 自动化 E2E |
| G-05 | CI 门禁 (覆盖率和 RTM) 正确生效 | TC-CONF-008 | 手动验证 CI 日志 |
| G-06 | SIL 测试在 CI L2 正确阻塞/放行 | TC-CONF-009 | 手动验证 CI 日志 |
| G-07 | 无 P0/P1 安全漏洞 | — | 安全扫描报告 |
| G-08 | 数据备份策略已确认 | — | 运维确认 |

### 5.2 软性门禁 (Should-Fix)

以下条件建议满足后再发布，但紧急情况下可有条件放行：

| # | 门禁条件 | 关联 TC | 宽容期限 |
|:-|:---------|:-------:|:--------|
| S-01 | Pro → Free 降级流程正常 | TC-CONF-003 | 1 个 Sprint |
| S-02 | Web UI 核心页面均可达 | TC-CONF-010 | 1 个 Sprint |
| S-03 | CLI 模板初始化正常 | TC-CONF-007 | 1 个 Sprint |
| S-04 | 所有 P1 确认测试通过 | — | 2 个 Sprint |

### 5.3 门禁判定流程

```
┌──────────────────────────────────┐
│ 收集确认测试结果                  │
├──────────────────────────────────┤
│                                  │
│ 检查 G-01 ~ G-08                 │
├──────────────────────────────────┤
│ 全部通过?                        │
│  ├─ YES → 检查 S-01 ~ S-04       │
│  │   ├─ 全部通过或已记录待办      │
│  │   │   → ✅ Go (发布)          │
│  │   └─ 重大偏离                 │
│  │       → 🟡 Conditional Go     │
│  │         (需签字确认)          │
│  └─ NO  → 记录失败的 G 条件      │
│           → 🔴 No-Go            │
└──────────────────────────────────┘
```

---

## 附录 A: 测试工具与框架

| 工具 | 用途 | 必需/可选 |
|:----|:-----|:---------:|
| pytest | 自动化测试框架 | ✅ 必需 |
| Playwright | E2E Web 测试 (TC-CONF-001, 004, 010) | ✅ 必需 |
| Stripe CLI | Webhook 模拟 (TC-CONF-002, 003, 006) | ✅ 必需 |
| QEMU | SIL 仿真测试 (TC-CONF-009) | ✅ 必需 |
| httpx | API 测试 (TC-CONF-005, 006) | ✅ 必需 |
| docker-compose | 环境编排 (Staging) | ✅ 必需 |
| jq | JSON 解析与断言辅助 | ✅ 必需 |

## 附录 B: 测试执行计划

| 阶段 | 时间 | 执行范围 | 负责人 |
|:----|:----|:---------|:------|
| Sprint 执行期 | 日常 | Dev 环境，按需触发 | 开发者 |
| Pre-Release | 发布前 3 天 | Dev + Staging，全量确认测试 | 小马 🐴 |
| Release Day | 发布当日 | Staging 全量 + Production Smoke | 小马 🐴 |
| Post-Release | 发布后 1 周 | Production 监控 + Smoke | 小马 🐴 |

## 附录 C: 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|:----|:----|:---------|:----|
| v1.0.0 | 2026-06-16 | 初版创建，覆盖 RS-014, RS-012, RS-013, RS-011 等 α Track 需求 | 小马 🐴 |
