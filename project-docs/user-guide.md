# yuleOSH v0.8.0 — User Guide

> Quick start for new users

---

## 🚀 3 分钟快速开始

> 从注册到运行第一条 Pipeline，三步搞定。

### 第 1 步：注册账号（30 秒）

1. 打开 **[app.yuleosh.com](https://app.yuleosh.com)**
2. 点击右上角 **「免费开始」** → 输入邮箱和密码
3. 查收验证邮件 → 点击确认链接 → ✅ 注册完成

> 无需信用卡，Free 套餐立即可用。

### 第 2 步：创建组织 + 项目（1 分钟）

登录后，引导向导会带你完成：

```
注册完成
  ↓
📋 创建组织 → 输入公司/团队名称（如 "Acme Corp"）
  ↓
📁 创建项目 → 输入项目名称（如 "Vehicle Controller"）
  ↓
✅ 进入项目 Dashboard
```

**贴士**：组织名和项目名可随时在「设置」中修改。每个组织下可以创建多个项目。

### 第 3 步：运行你的第一条 Pipeline（1 分钟 30 秒）

在项目 Dashboard 中：

1. **上传规格文档** — 点击「导入 Spec」→ 选择或粘贴一个 OpenSpec 格式的 `.md` 文件
   *(如果还没有，使用下方模板快速创建一个)*
2. **运行 Pipeline** — 在 Spec 页面点击 **「▶ 运行 Pipeline」**
3. **查看结果** — 等待 30–60 秒 → Pipeline Dashboard 显示：

```
✅ 需求解析完成
✅ 代码审查报告（如果是 Pro/Enterprise）
✅ 追溯矩阵
✅ 证据包可下载
```

> 🎉 就这么简单！你已经完成了你的第一条嵌入式开发自动化 Pipeline。

### 最小规格模板

保存为 `my-spec.md` 并上传到项目中：

```markdown
# My First Spec

## Requirements

### RS-001: System Initialization
Status: PROPOSED

The system SHALL initialize within 500ms of power-on.

#### Scenario: Normal Boot
GIVEN the system is powered off
WHEN power is applied
THEN the system SHALL report ready within 500ms
```

---

## 📺 流程概览（文本版）

如果你希望跟随视频/GIF 教程，以下是关键流程的逐帧描述：

```
┌─────────────────────────────────────────────────────────┐
│  注册 → 登录 → 创建组织 → 创建项目 → Dashboard          │
│                        ↓                                │
│                 导入规格文档 (.md)                        │
│                        ↓                                │
│             运行 Pipeline（~1 分钟）                    │
│                        ↓                                │
│   ┌───────────────────┼───────────────────┐            │
│   ↓                   ↓                   ↓            │
│ 审查报告          追溯矩阵          证据包下载          │
│ (代码/需求)      (SHALL 追溯)     (合规 ZIP)           │
└─────────────────────────────────────────────────────────┘
```

**逐屏说明：**

| 画面 | 内容 | 操作 |
|:----|:----|:-----|
| **首页** | CTA "免费开始使用" + GitHub 链接 | 点击「免费开始」|
| **注册页** | 邮箱输入框 + 密码 + 提交按钮 | 填写并提交 |
| **验证邮件** | 确认链接 | 点击链接 |
| **引导页** | 创建组织表单 | 输入组织名 |
| **创建项目** | 项目名称 + 可选描述 | 输入并点击创建 |
| **Dashboard** | 项目卡片 + 快速操作 | 点击进入项目 |
| **Spec 页面** | 上传区域 + 编辑器预览 | 上传/粘贴 spec |
| **Pipeline 运行页** | 进度条 + 日志流 | 等待完成 |
| **结果页** | 审查报告 + 追溯矩阵 | 浏览 / 下载证据 |

---

## 🔄 常见场景

### 场景 A：导入 spec → 运行 Pipeline → 审查报告 → 打包证据

这是最核心的使用路径，适用于**已有规格文档**的嵌入式项目。

```
开始
 │
 ├─ ① 导入 spec.md
 │    支持格式：OpenSpec Markdown（.md）
 │    上传方式：拖拽 / 粘贴 / CLI（curl / yuleosh CLI）
 │    → 系统自动解析 SHALL/SHOULD/MAY + GIVEN/WHEN/THEN
 │
 ├─ ② 运行 Pipeline
 │    在全功能（Pro/Enterprise）模式下执行：
 │    ├── SDD → 设计规格分解
 │    ├── DDD → 详细设计生成
 │    ├── TDD → 测试用例生成
 │    ├── CI Layer 1 → 单元测试 + 覆盖率
 │    ├── CI Layer 2 → 集成测试 + 静态分析
 │    └── CI Layer 2.5 → HIL（Enterprise）
 │
 ├─ ③ 查看审查报告
 │    AI Code Review 返回四维度报告：
 │    ├── 架构审查 → 依赖分析、层违规
 │    ├── 领域审查 → 需求覆盖率 %、未实现的 SHALL
 │    ├── 风格审查 → MISRA C / AUTOSAR C++ 检查
 │    └── 覆盖率审查 → 行/分支/MC/DC 覆盖
 │
 └─ ④ 打包证据
    一键导出合规包（ZIP）：
     ├── 追溯矩阵 (CSV/JSON)
     ├── 测试报告
     ├── 覆盖率报告
     ├── AI 审查日志
     └── 签名的完整性摘要
```

**CLI 版本（适合 CI/CD 集成）：**

```bash
# 1. 导入规格
yuleosh spec import --project vcu --file docs/spec.md

# 2. 运行 Pipeline
yuleosh pipeline run --project vcu --spec docs/spec.md

# 3. 查看审查报告
yuleosh review get --run-id abc123

# 4. 导出证据包
yuleosh evidence pack --run-id abc123 --output evidence-v1.0.zip
```

### 场景 B：从零开始一个新嵌入式项目

```
① 创建组织 + 项目     → 在 Dashboard 中操作（~2 分钟）
② 用 OpenSpec 写规格  → 使用模板或编辑器（项目依赖，几小时到几天）
③ 导入 spec 运行 Pipeline → 一键执行（~1 分钟）
④ 迭代 ②+③          → 修改 spec → 重新运行 → 对比差异
⑤ 最终导出证据包      → 用于审计/交付
```

### 场景 C：将 yuleOSH 接入现有 CI/CD

```yaml
# .github/workflows/yuleosh-pipeline.yml
name: yuleOSH Pipeline
on: [push]
jobs:
  pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install yuleOSH CLI
        run: pip install yuleosh-cli
      - name: Run Pipeline
        run: |
          yuleosh pipeline run \
            --project ${{ vars.YULEOSH_PROJECT }} \
            --spec docs/spec.md \
            --api-key ${{ secrets.YULEOSH_API_KEY }}
      - name: Export Evidence
        run: yuleosh evidence pack --run-id $(yuleosh pipeline last-run-id)
```

### 场景 D：多项目多团队协作

```
Enterprise 推荐配置:
┌─ 组织 "Acme Corp"
│   ├─ 项目 "VCU (Vehicle Controller)"
│   │   ├─ 团队成员: 3 人
│   │   ├─ 规格: vcu-spec.md
│   │   └─ Pipeline: 小时级运行
│   │
│   ├─ 项目 "BCM (Body Controller)"
│   │   ├─ 团队成员: 2 人
│   │   ├─ 规格: bcm-spec.md
│   │   └─ Pipeline: 日级运行
│   │
│   └─ 项目 "Digital Key"
│       ├─ 团队成员: 5 人
│       ├─ 规格: dk-spec.md (ICC E/CCC/ICCOA)
│       └─ Pipeline: 每次提交触发
```

---

## ⚠️ 新手常见错误与解决方案

### 错误 1：忘记了 Pipeline 运行次数限制

**现象**：点击「运行 Pipeline」后提示 "Free 计划每月仅 10 次，已用完"。
**原因**：Free 套餐每月 10 次 Pipeline 运行，超出后需等待重置或升级。
**解决**：
- 升级到 **Pro**（¥299/月，无限 Pipeline 运行）
- 或在 Free 额度内只在对 Spec 有实质性修改时才运行

### 错误 2：Spec 格式不符合 OpenSpec 规范

**现象**：导入 spec 后，追溯矩阵为空或某些需求未被识别。
**原因**：需求没有使用正确关键词（SHALL / SHOULD / MAY）或场景未按 GIVEN/WHEN/THEN 格式书写。
**解决**：
```
❌ 错误写法: "系统初始化需在 500ms 内完成"
✅ 正确写法: "The system SHALL initialize within 500ms"
❌ 错误写法: "测试场景：系统启动时，检查时间"
✅ 正确写法: "GIVEN the system is powered off\nWHEN power is applied\nTHEN the system SHALL report ready within 500ms"
```
**快速修复**：在 Spec 页点击「格式检查」→ 系统会自动标注未识别的需求行。

### 错误 3：登录时 "Password required" 但没设密码

**现象**：使用 `email` 登录时提示需要 `password`。
**原因**：注册时设了密码，但调用的 API 没传 `password` 字段。
**解决**：
```bash
# 正确请求
curl -X POST https://your-domain.com/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"you@company.com", "password":"YourPassword123"}'
```

### 错误 4：自托管部署后无法访问

**现象**：Docker 启动后 `http://localhost:8080` 打不开。
**常见原因与排查**：

| 可能原因 | 检查方法 | 修复 |
|:---------|:---------|:-----|
| Docker 未运行 | `docker ps` | `docker-compose up -d` |
| 端口冲突 | `lsof -i :8080` | 修改 `docker-compose.yml` 中的端口映射 |
| 防火墙阻止 | `curl localhost:8080` | 检查服务器防火墙规则 |
| 数据库未就绪 | `docker logs yuleosh-db-1` | 等待 30 秒后重试 |

### 错误 5：API Key 过期

**现象**：CI/CD 脚本中调用 yuleOSH API 返回 401 Unauthorized。
**解决**：
1. 在 Dashboard → 设置 → API Keys 中生成新 Key
2. 更新 CI/CD 环境变量中的 `YULEOSH_API_KEY`
3. 定期轮换 Key（建议每 90 天）

### 错误 6：Pipeline 运行失败但日志没看懂

**现象**：Pipeline 状态显示 ❌ Red，但错误信息是 "exit code 1"。
**解决**：
1. 点击 Pipeline 日志详情 → 搜索 `ERROR` 或 `FAIL`
2. 检查 Spec 文件中是否有不合法的字符或空行
3. 确认交叉编译链镜像已正确配置
4. 如果仍无法解决 → 
   - Free: 在 GitHub Issues 贴出匿名日志
   - Pro: 发邮件至 support@yuleosh.com（附 Pipeline 运行 ID）
   - Enterprise: 联系专属工程师

### 错误 7：忘记组织名或项目名

**现象**：登录后在 Dashboard 看不到项目。
**解决**：
- 在 Dashboard 右上角头像 → 「我的组织」→ 查看你的所有组织
- 如果组织不存在，可能需要通过邀请链接重新加入
- 联系组织管理员获取准确的 org slug

---

## Getting Started (5 minutes)

> 此章节为 CLI 用户参考，SaaS 用户推荐使用上方的「3 分钟快速开始」。

### 1. Sign Up

```bash
# Step 1: Visit your yuleOSH instance
open https://your-domain.com

# Step 2: Sign in with your email
curl -X POST https://your-domain.com/api/auth/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"you@company.com"}'
# → {"token":"***", "redirect":"/org/setup", "needs_org":true}
```

### 2. Create Your Organization

```bash
curl -X POST https://your-domain.com/api/org/create \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "org_name":"Acme Corp",
    "org_slug":"acme",
    "project_name":"Vehicle Controller",
    "project_slug":"vcu",
    "email":"you@company.com",
    "password":"YourSecurePassword123"
  }'
```

### 3. Configure Your Project

Create `docs/spec.md` with your requirements:

```markdown
# Vehicle Controller Spec

## Requirements

### RS-001: CAN Bus Communication
Status: PROPOSED

The VCU SHALL communicate via CAN bus at 500kbps.

#### Scenario: CAN Message Transmission
GIVEN a CAN bus is connected
WHEN the VCU sends a message
THEN the message SHALL be received within 10ms
```

### 4. Run Your First Pipeline

```bash
# Validate your spec
python3 -m src.spec.validate docs/spec.md

# Run CI Layer 1 (unit tests)
python3 -m src.ci.run 1

# Run full pipeline
python3 -m src.ci.run all
```

### 5. View Results

```bash
# Health check
curl https://your-domain.com/api/health

# Evidence pack
curl https://your-domain.com/api/v1/evidence

# Traceability matrix
curl https://your-domain.com/api/v1/evidence/traceability
```

---

## Pipeline Overview

```
CI Layer 1 → Development Verification
  ├── plan-lint
  ├── clang-tidy
  ├── unit tests
  └── coverage check

CI Layer 2 → Integration Verification
  ├── cross-compile (ARM/RISC-V)
  ├── static analysis
  ├── SIL tests (QEMU)
  └── integration tests

CI Layer 2.5 → HIL Testing
  ├── hardware detection
  ├── flash firmware
  └── serial assertions

CI Layer 3 → System Verification
  ├── E2E tests
  ├── version check
  └── evidence pack
```

---

## Multi-Tenant Features

| Feature | Description |
|:--------|:------------|
| Organizations | Isolated workspaces with own users and projects |
| Projects | Per-project specs, pipelines, and evidence |
| Roles | admin (full access) / member (read + run) |
| Invite Codes | Share org slug to invite team members |
| API Keys | Per-org keys for CI/CD integration |

---

## Troubleshooting

| Problem | Solution |
|:--------|:---------|
| "Password required" | User has password set — include `password` in signin |
| "Invalid password" | Wrong password — use `/api/auth/signin` to retry |
| "Too many attempts" | Rate limited — wait 5 minutes |
| "Organization not found" | Check invite code / org slug |
| "Unauthorized" | Token expired — sign in again |

---

## Onboarding Quick Reference Card

> 打印这个卡片，贴在你的工位上。

```
┌─────────────────────────────────────────────────────────────┐
│               yuleOSH 快速参考卡                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🅐  注册       app.yuleosh.com → 免费开始                 │
│                                                             │
│  🅑  创建组织   引导页 → 输入团队/公司名称                   │
│                                                             │
│  🅒  创建项目   输入项目名称 → 进入 Dashboard                │
│                                                             │
│  🅓  导入 Spec  拖拽 .md 文件或粘贴 OpenSpec 内容            │
│                                                             │
│  🅔  运行       点击「▶ 运行 Pipeline」→ 等待 30-60 秒      │
│                                                             │
│  🅕  查看结果   → 审查报告 / 追溯矩阵 / 证据包下载           │
│                                                             │
│  ❓ 遇到问题？                                               │
│     Free:  GitHub Issues                                    │
│     Pro:    support@yuleosh.com (48h)                        │
│     Enterp: 专属工程师                                       │
└─────────────────────────────────────────────────────────────┘
```
