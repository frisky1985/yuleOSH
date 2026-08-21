# yuleOSH Dashboard 设计说明（v1.0）

> **版本**: v1.0 · 2026-08-15
> **状态**: 设计草案（老板头脑风暴产出）
> **关联**: 产品说明书 Phase 1 "组织级看板产品化" · 设备管理层（已落地 S1-S4）

---

## 一、设计目标

让 yuleOSH 从"单机 CLI 工具"进化为"团队协作平台"。Dashboard 是团队日常工作的入口，8 大模块覆盖：**管人（角色）→ 管需求 → 管流水线 → 管产出物 → 管测试 → 管设备 → 管日志 → 管数据**。

### 用户故事（北极星）

> **质量经理王工**早上打开 Dashboard：
> 1. 看到"数据座舱"——昨晚 3 条流水线的合规状态、覆盖率趋势、MISRA 违规数
> 2. 点进一条失败流水线 → 看到失败阶段产出物 → 关联测试日志 → 定位到设备
> 3. 把测试日志@给开发者 → 开发者修完重跑 → 证据包自动更新
> 4. 审计前 5 分钟生成证据包 ZIP，不用翻 Excel

**一句话**：Dashboard = **从需求到证据的团队协作控制台**。

---

## 二、总体架构

### 2.1 页面/导航结构

```
yuleOSH Dashboard
├── ① 数据座舱（首页）          — 全局状态总览
├── ② 需求管理                  — OpenSpec 需求看板
├── ③ 流水线管理                — Pipeline 列表/详情/重跑
│     └── 阶段产出物管理         — 每步产出物浏览/下载
├── ④ 测试用例管理              — 三层测试用例库 + 结果
├── ⑤ 设备管理                  — 板卡池状态/分配/健康
├── ⑥ 测试日志管理              — 串口/CI 日志检索
├── ⑦ 角色管理                  — 组织/成员/权限
└── ⑧ 系统设置                  — 项目/API Key/通知
```

### 2.2 技术分层

```
┌──────────────────────────────────────────────┐
│ 前端：Next.js 静态导出（现状）→ SPA 增强      │
│   页面路由 + API 客户端 + 状态管理            │
├──────────────────────────────────────────────┤
│ API 层：/api/v1/*（现有 router 扩展）         │
│   dashboard / pipeline / test / device /     │
│   artifact / log / role / requirement        │
├──────────────────────────────────────────────┤
│ 领域层：yuleosh.* 现有模块                    │
│   pipeline / ci / device / spec / review /   │
│   evidence / audit / knowledge / store       │
├──────────────────────────────────────────────┤
│ 存储：SQLite（本地） / PostgreSQL（生产）     │
│   projects / pipelines / ci_runs / reviews / │
│   evidence / devices / allocations / events  │
└──────────────────────────────────────────────┘
```

### 2.3 设计原则

1. **数据真实优先**：Dashboard 只显示真实业务数据；无数据时显式标注"无数据"，不用假数据充数（对齐现有 dashboard API "projects real-data-only" 原则）
2. **三层权限**：组织 → 项目 → 资源，RBAC 控制每一层
3. **可钻取**：座舱 → 流水线 → 阶段 → 产出物 → 日志，逐层下钻
4. **证据闭环**：任何产出物/日志都可在证据包中追溯（对齐 ASPICE 审计链）

---

## 三、8 大模块详细设计

### 模块 ①：角色管理（Role Management）

**目标**：组织级成员与权限管理，支撑"团队协作"。

#### 角色设计（RBAC）

| 角色 | 权限等级 | 典型职责 |
|---|---|---|
| **Owner** | 全部 | 组织管理、计费、删除项目 |
| **Admin** | 全部 - 计费 | 成员管理、项目创建、设备管理、角色分配 |
| **Quality Manager** | 读 + 合规操作 | 看板、证据包生成、差距分析、测试日志审计 |
| **Architect** | 读 + 设计操作 | 需求审批、架构评审、流水线配置 |
| **Developer** | 读 + 开发操作 | 跑流水线、看测试结果、上传日志 |
| **Viewer** | 只读 | 审计员、外部协作 |

#### 功能点

- 成员管理：邀请 / 移除 / 改角色（`/api/v1/org/members`）
- 项目级权限：项目成员列表，每项目可设 Admin/Dev/Viewer
- 审计日志：谁在什么时候改了什么权限（append-only）
- SSO 对接（Enterprise）：LDAP/SAML 同步角色

#### 数据模型

```
organizations (id, name, slug)
org_members (org_id, user_id, role)          # 组织角色
project_members (project_id, user_id, role)  # 项目角色
role_permissions (role, resource, action)    # 权限矩阵
```

#### API 草案

```
GET  /api/v1/org/members              # 成员列表
POST /api/v1/org/members/invite       # 邀请成员
PATCH /api/v1/org/members/{id}        # 改角色
GET  /api/v1/projects/{id}/members    # 项目成员
GET  /api/v1/roles                    # 角色权限矩阵
```

---

### 模块 ②：需求管理（Requirements Management）

**目标**：OpenSpec 需求的全生命周期看板。

#### 功能点

- 需求列表：ID、标题、状态（PROPOSED→APPROVED→IMPLEMENTED→VERIFIED）、优先级
- 需求详情：SHALL/SHOULD/MAY 内容 + GIVEN/WHEN/THEN 场景
- 需求状态流转：审批 / 变更 / 影响分析
- **追溯视图**：需求 ↔ 设计 ↔ 代码 ↔ 测试 ↔ 证据（traceability matrix）
- 差距分析：哪些需求没有实现/测试/证据（对齐 SWE.1 合规）

#### 数据模型

```
spec_requirements (id, spec_id, req_id, text, kind, state, priority)
spec_scenarios (id, requirement_id, given, when, then)
requirement_trace (requirement_id, artifact_type, artifact_id)
```

#### API 草案

```
GET  /api/v1/spec/requirements?project=xxx
GET  /api/v1/spec/requirements/{id}
PATCH /api/v1/spec/requirements/{id}/state
GET  /api/v1/spec/trace/{req_id}
GET  /api/v1/spec/gaps
```

---

### 模块 ③：流水线管理（Pipeline Management）

**目标**：查看/触发/重跑 36 步 AI 流水线。

#### 功能点

- 流水线列表：run_id、spec、状态（completed/failed/running）、时长、Token 消耗
- 流水线详情：**36 步时间线**，每步状态（✅/❌/⏭️）、耗时、Agent 角色
- 操作：触发新 run / 重跑失败步骤 / 从指定步骤续跑（`--from-step`）
- 步骤日志：每步输出（LLM 调用、工具执行、verdict）
- 失败诊断：错误列表 + 建议修复（对齐 PipelineStepError）

#### 数据模型（复用现有）

```
pipelines (id, name, status, created_at, ...)        # 现有
pipeline_steps (pipeline_id, step_id, status, agent, # 现有 session steps
                started_at, completed_at, output_path)
```

#### API 草案

```
GET  /api/v1/pipeline/list                 # 已有
GET  /api/v1/pipeline/status/{id}          # 已有
POST /api/v1/pipeline/trigger              # 已有
POST /api/v1/pipeline/{id}/retry           # 重跑失败步骤
POST /api/v1/pipeline/{id}/resume          # 从指定步骤续跑
GET  /api/v1/pipeline/{id}/steps/{sid}/log # 步骤日志
```

---

### 模块 ④：阶段产出物管理（Artifact Management）

**目标**：流水线每个阶段生成的产出物集中管理，可浏览/下载/追溯。

#### 产出物清单（36 步流水线）

| 阶段 | 产出物 |
|---|---|
| spec-check | spec.md |
| super-analysis | startup-analysis.md |
| prd | prd.md + prd-review.json |
| architecture | architecture.md + arch-review.json |
| development-plan | development-plan.md |
| codegen | artifacts/generated-code/<run>/ |
| codegen-deploy | codegen-deploy.json |
| self-test | self-test-report.md |
| c-unit-test | c-unit-test.json |
| integration-test | integration-test.json |
| code-review | code-review.json |
| misra-review | misra-review.json |
| c-coverage-gate | c-coverage-gate.json + c-coverage.json |
| qualification | qualification-test.json |
| final-report | final-report.md + 证据包 |

#### 功能点

- 按 run 列出所有产出物（树状：阶段 → 文件）
- 在线预览（Markdown/JSON/文本）
- 下载单个 / 下载整个证据包 ZIP
- 追溯：产出物 ↔ 需求 ↔ 测试（traceability）

#### 数据模型

```
pipeline_artifacts (id, pipeline_id, step_id, path, type, size, sha256)
```

#### API 草案

```
GET /api/v1/pipeline/{id}/artifacts
GET /api/v1/pipeline/{id}/artifacts/{aid}/content   # 预览
GET /api/v1/pipeline/{id}/artifacts/{aid}/download
GET /api/v1/pipeline/{id}/evidence-pack             # 证据包 ZIP
```

---

### 模块 ⑤：测试用例管理（Test Case Management）

**目标**：三层测试（单元/集成/系统）用例库 + 执行结果管理。

#### 三层测试视图（2026-08-15 落地）

| 层 | 载体 | 运行器 |
|---|---|---|
| 单元 | C 单测（ctest -LE integration） | c-unit-test step |
| 集成 | C 集成测试（ctest -L integration） | integration-test step |
| 系统 | pytest 合格性测试 | test-qualification step |

#### 功能点

- 用例库：三层分类、用例名称、所属模块、状态
- 执行历史：每次 run 的通过/失败/跳过、耗时、关联流水线
- 失败详情：失败断言、日志片段、关联设备
- 覆盖率视图：line/branch/function 每文件
- 回归趋势：最近 N 次执行的通过率

#### 数据模型

```
test_cases (id, project_id, layer, name, module, status)
test_runs (id, case_id, pipeline_id, status, duration, output, device_id)
coverage_reports (id, project_id, pipeline_id, line_rate, branch_rate, files)
```

#### API 草案

```
GET  /api/v1/tests?project=xxx&layer=unit
GET  /api/v1/tests/{id}/runs
POST /api/v1/tests/{id}/rerun
GET  /api/v1/tests/coverage?project=xxx
GET  /api/v1/tests/trend?project=xxx
```

---

### 模块 ⑥：设备管理（Device Management）

**目标**：HIL 板卡池可视化（设备管理层 S1-S4 已落地，此模块做 UI）。

#### 功能点

- 设备总览：状态卡片（ONLINE/BUSY/OFFLINE/FAULT/UNKNOWN）彩色分布
- 设备详情：平台、flasher、串口、当前占用 job、固件版本、最后心跳
- 分配操作：手动 acquire/release（调试）
- 健康监控：看门狗事件时间线（registered/online/offline/fault/recovered）
- 设备利用率：每块板的占用时间占比

#### 数据模型（复用 device 模块）

```
devices / allocations / device_events（已落地）
```

#### API 草案

```
GET  /api/v1/device/list                    # 设备状态
GET  /api/v1/device/{id}                    # 详情
POST /api/v1/device/{id}/acquire            # 分配
POST /api/v1/device/{id}/release            # 释放
GET  /api/v1/device/{id}/events             # 事件时间线
GET  /api/v1/device/stats                   # 利用率
```

---

### 模块 ⑦：测试日志管理（Test Log Management）

**目标**：串口日志 / CI 日志 / 测试输出的统一检索与关联。

#### 日志来源

| 来源 | 内容 | 格式 |
|---|---|---|
| 串口（HIL） | 设备运行日志 | 文本流 |
| CI 输出 | ctest/pytest/gcovr 输出 | 文本 |
| 流水线步骤 | 每步 stdout/stderr | 文本 |
| 审计日志 | append-only 操作记录 | JSON |

#### 功能点

- 统一检索：跨来源全文搜索（时间/设备/流水线/关键词）
- 时间线视图：一次 HIL 测试的完整日志流
- 关联：日志 ↔ 测试用例 ↔ 流水线 ↔ 设备
- 导出：单日志 / 打包进证据包
- 告警：ERROR/FAIL/异常模式高亮 + 规则告警

#### 数据模型

```
test_logs (id, project_id, source, device_id, pipeline_id,
           test_run_id, content, level, created_at)
log_index (FTS5 全文索引)
```

#### API 草案

```
GET /api/v1/logs?query=&device=&pipeline=&time_from=&time_to=
GET /api/v1/logs/{id}
GET /api/v1/logs/{id}/context
GET /api/v1/logs/export
```

---

### 模块 ⑧：数据座舱（Data Cockpit）

**目标**：全局状态一屏总览，管理者的"第一屏"。

#### 核心指标卡

```
┌────────────────────────────────────────────────────────┐
│  数据座舱（首页）                                        │
├──────────┬──────────┬──────────┬──────────┬───────────┤
│ 合规总分  │ SWE.1-6  │ 覆盖率   │ MISRA    │ 活跃流水线│
│ 78/100   │ 5/6 ✅   │ 82.4%    │ 12 违规  │ 3 运行中  │
├──────────┴──────────┴──────────┴──────────┴───────────┤
│  SWE 雷达图        │  覆盖率趋势（30 天）               │
│  SWE.1 ═══════      │  ▁▂▃▅▆▇▇▆                       │
│  SWE.2 ════════     │                                   │
│  SWE.3 ═════        │  MISRA 违规趋势                   │
│  SWE.4 ═══════      │  ▇▅▃▂▁                           │
│  SWE.5 ══════════   │                                   │
│  SWE.6 ═══          │                                   │
├─────────────────────┴───────────────────────────────────┤
│  最近流水线（可下钻）│  设备状态（可下钻）│  待办/告警    │
└─────────────────────────────────────────────────────────┘
```

#### 指标定义

| 指标 | 来源 | 计算 |
|---|---|---|
| 合规总分 | evidence | SWE.1-6 各 BP 通过率加权 |
| 覆盖率 | coverage | line_rate 汇总（gcovr） |
| MISRA 违规 | misra | 违规数（按严重级） |
| 测试通过率 | test_runs | 最近 100 次 run 通过率 |
| 设备利用率 | device_events | BUSY 时间 / 总时间 |
| Pipeline 成功率 | pipelines | 最近 30 天 completed/failed |

#### API 草案

```
GET /api/v1/dashboard/overview        # 指标卡
GET /api/v1/dashboard/swe-status      # 已有
GET /api/v1/dashboard/coverage-trend  # 已有
GET /api/v1/dashboard/misra-trend     # 已有
GET /api/v1/dashboard/recent-pipelines
GET /api/v1/dashboard/device-status
```

---

## 四、权限矩阵（角色 × 模块）

| 模块 | Owner | Admin | Quality Mgr | Architect | Developer | Viewer |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| 数据座舱 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| 需求管理 | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| 流水线管理 | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| 阶段产出物 | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| 测试用例 | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| 设备管理 | ✅ | ✅ | 👁 | 👁 | 👁 | 👁 |
| 测试日志 | ✅ | ✅ | ✅ | ✅ | ✅ | 👁 |
| 角色管理 | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |

> ✅ = 全部操作 · 👁 = 只读 · ❌ = 无权限

---

## 五、技术方案

### 5.1 前端

- **现状**：Next.js 静态导出（frontend/out）+ 原生 dashboard.html
- **规划**：保留静态导出架构（无需 Node 运行时），API 走 fetch 调 `/api/v1/*`
- **组件化**：复用现有页面风格，新增模块各自独立 HTML 页面 + 共享 JS 工具
- **图表**：轻量 SVG/CSS 图表（避免重依赖），或引入 Chart.js（按需）

### 5.2 后端

- API 路由：扩展 `api/router.py` 懒加载 handlers（对齐 AR-P2-01 模式）
- 新增 handlers：
  - `api/dashboard_v2.py`（座舱聚合）
  - `api/artifacts.py`（产出物）
  - `api/tests.py`（测试用例）
  - `api/logs.py`（日志检索）
  - `api/device_ui.py`（设备 UI，复用 device 模块）
  - `api/members.py`（角色管理）
- 存储：现有 store.py 加表 + device.db（设备独立库）

### 5.3 安全

- 全 API 走 `require_auth`（现有中间件）
- RBAC 校验中间件：`require_role("admin")` 等
- 日志检索防注入：FTS5 参数化
- 产出物下载：路径穿越防护（只允许 pipeline 产出目录内）

---

## 六、落地顺序（Phase 1）

| 步骤 | 内容 | 依赖 | 优先级 |
|---|---|---|---|
| D1 | 数据座舱（overview + 指标卡） | 现有 dashboard API | P0 |
| D2 | 流水线管理 + 阶段产出物 | 现有 pipeline API | P0 |
| D3 | 设备管理 UI | device 模块（已落地） | P0 |
| D4 | 测试用例 + 日志检索 | test/log 表 | P1 |
| D5 | 需求管理 UI | spec API | P1 |
| D6 | 角色管理 | org/members 表 | P1 |

---

## 七、关键决策（推荐结论，2026-08-15）

> 基于现状核实（Next.js 16.3 静态导出 + React 19 + shadcn 已落地；dashboard 现有页面全为自绘 SVG；后端 device/ + rbac/ 模块已就绪），以下为推荐方案，可直接执行。

| # | 决策点 | 推荐 | 理由 |
|---|---|---|---|
| 1 | 前端技术 | **继续 Next.js 静态导出，不引入 Vite** | 现有 frontend/ 已是 Next.js 16.3 + shadcn + 静态导出（`next build && inject-meta-csp.py`），换 Vite 是推倒重来零收益 |
| 2 | 图表库 | **自绘 SVG 优先，复杂图按需引入 Chart.js** | 现有页面（coverage/misra 趋势）已全是自绘 SVG，零依赖；36 步流水线甘特图等复杂场景再加 Chart.js。ECharts 太重，内部工具用不上 |
| 3 | 角色粒度 | **固定 6 角色 + 可配置权限点，不做自定义角色 UI** | 团队内部工具 6 角色够用；RBAC 权限点（permission）存库可配，留扩展入口但不做角色编辑器（YAGNI） |
| 4 | 日志保留 | **结构化日志永久保留；原始串口/调试日志滚动 90 天（可配）** | 审计/证据链日志是合规资产不能丢；串口原始日志量大价值递减，90 天 + 总量上限即可 |
| 5 | 座舱合规总分 | **五维加权可配置，默认权重：覆盖率 30 / 测试通过率 25 / MISRA 违规 20 / 需求追溯 15 / 证据完整性 10** | 不追求"单一神分数"，座舱同时显示分项 + 权重，权重可调；分数只做趋势参考，不进流水线门禁 |
| 6 | 设备 UI 权限 | **Developer 可 acquire/release 刷板，但注册/删除/配置仅 Admin/QM** | 开发日常要刷板（看门狗时长约束防独占）；设备资产登记与策略属于管理职责，避免误删/误配 |

### 执行顺序（P0 先行）

1. **D1 数据座舱增强**（已有 overview/gap-analysis/knowledge-base/misra-trends 四个 Tab，补合规总分五维卡）
2. **D2 流水线管理 + 阶段产出物**（pipeline API 已有，前端加时间线/产出物浏览）
3. **D3 设备管理 UI**（device 后端已落地，纯前端增量）
4. **D4 测试用例管理 → D5 测试日志 → D6 角色管理 → D7 需求管理**（P1，按依赖排）

---

*本设计基于 yuleOSH v4.0.0 现有架构 + 设备管理层（已落地）+ 产品说明书 Phase 1 规划。*
