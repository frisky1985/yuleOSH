# 项目管理 SOP - 全自动 Agent 流水线 v3.0

> OpenSpec + Superpowers + Harness Engineering 三位一体（OSH-Fusion）

---

## ⚡ 新增：量产级前置规划（每次项目启动必须执行）

> **2026-06-27 新增** — 之前 Demo 范式错误的教训：必须把项目放在 yuleOSH 生态系统和量产要求下规划。

### Step 0: 量产就绪检查清单

**在进入正式流水线之前，必须先确认以下信息并写入 `project-context.md`：**

#### 0.1 目标硬件平台
| 问题 | 选项 | 决策 |
|:-----|:-----|:-----|
| MCU 型号？ | S32K312 / i.MX8M Mini / 其他 | 「老板，目标 MCU 是什么？」 |
| 外设需求？ | CAN/CAN FD/Ethernet/LIN/ADC/PWM | 从需求导出 |
| RAM/Flash 大小？ | 需估算 | 架构阶段细化 |

#### 0.2 ASIL 目标
| 问题 | 选项 |
|:-----|:-----|
| 目标 ASIL 等级？ | QM / ASIL-A / ASIL-B / ASIL-C / ASIL-D |
| 安全关键功能？ | 列出哪个功能需要 ASIL 等级 |

#### 0.3 BSW 平台
| 组件 | 来源 | 状态 |
|:-----|:-----|:----:|
| MCAL | yuleASR (MCAL 21 模块) | 按目标 MCU 选型 |
| ECUAL | yuleASR (ECUAL 29 模块) | CanIf/EthIf/MemIf 等 |
| Services | yuleASR (Services 44 模块) | COM/DCM/DEM/NvM/PduR/OS |
| RTE | yuleASR 或工具生成 | 配置 ARXML 生成 |
| Crypto | yuleASR (mbedTLS/SecOC) | 根据 ASIL 需求 |

#### 0.4 工具链
| 工具 | 用途 |
|:-----|:-----|
| yuleASR ARXML parser | 导入系统设计 → 生成 BSW 配置 |
| yuleASR config generator | 从 ARXML 生成 C 代码 |
| yuleASR CAN Config Tool | DBC/CSV → CAN 配置 |
| yuleASR DTC Configurator | JSON/CSV → DTC 配置 |
| MISRA checker | 静态分析 (yuleASR 已支持 MISRA C:2012) |

#### 0.5 产出物
- `project-context.md` — 硬件/软件/安全/工具链决策记录

---

## ⚡ Task-Init Hook — 替代定时握手检查

> 取代原「每15分钟握手检查」cron job。改为老板下发任务时触发唤醒。

### 触发时机

每次小明接收老板的新任务时，**在第一时间**执行以下 Hook 流程：

### Hook 流程（唤醒 → 握手 → 就绪）

```
[老板下发任务]
   │
   ├── Step 1: agents_list()
   │     ├── 检查 main / claude-agent / hermes-agent 全部存在
   │     └── 有缺失 → 检查配置文件 + 修复（自动）
   │
   ├── Step 2: 检测各 agent 在线状态
   │     ├── 对 claude-agent → sessions_spawn(agentId="claude-agent", task="alive", mode="run", cleanup="delete")
   │     ├── 对 hermes-agent → sessions_spawn(agentId="hermes-agent", task="alive", mode="run", cleanup="delete")
   │     ├── 15s内返回 → ✅ 在线
   │     └── 超时/失败 → 进入修复流程
   │
   ├── Step 3: 同步一次
   │     ├── 在线确认后，发简要同步消息：新任务名称+类型
   │     ├── 给小马: "新任务即将下发，准备撰写 spec"
   │     └── 给小克: "新任务即将下发，准备架构设计"
   │
   └── Step 4: 全部就绪 → 进入正常流水线
```

### 任务执行中的保活机制

当流水线进行到需要某个 agent 执行时（小克开发 → 小马审查等）：

1. 路由工作前先 `sessions_spawn()` 检测目标 agent 是否可达
2. 在线 → 正常发送工作指令
3. 掉线 → 自动执行 Layer 1 修复（session 重试 ×3，间隔30s）
4. Layer 1 失败 → Layer 2（forceNew 重建 session）
5. 全部失败 → **通知老板** 该 agent 失联，请求手动重启网关

### 与旧机制的区别

| 维度 | 旧 cron 机制 | 新 Hook 机制 |
|------|-------------|-------------|
| 触发 | 每15分钟无差别轮询 | 任务下发时按需触发 |
| 频率 | 高频（96次/天） | 低频（仅任务级） |
| 资源消耗 | 一直占用模型推理 | 仅任务时占用 |
| 错误率 | 连续超时（Timeout40s） | 无内置超时风险 |
| 保活策略 | 固定间隔，与任务流脱节 | 按需检测，与工作流绑定 |

---

## 🔒 新增：ISO 26262 功能安全集成到流水线

> **2026-06-27 新增** — 量产级软件必须覆盖功能安全工作产品，至少到 ASIL-A/B 级别。

### ISO 26262 在流水线中的位置

在每个项目阶段，集成对应的功能安全活动：

| 流水线阶段 | 对应 ISO 26262 工作产品 | 产出物 |
|:-----------|:------------------------|:-------|
| 前置规划 | Item Definition, HARA | `safety-concept.md` (HARA 表 + Safety Goals) |
| Spec 编写 | Functional Safety Concept, FSR | `safety-requirements.md` (含 ASIL 等级的 SHALL) |
| 架构设计 | Technical Safety Concept, TSR | `safety-architecture.md` (FTA + FMEA + ASIL 分解) |
| 开发 | 安全机制实现 | 代码中嵌入 safety mechanism |
| 测试 | 安全验证 + 覆盖率 | 故障注入测试 + 安全覆盖率报告 |
| 审查 | 安全评审 | `safety-review.md` (含安全异常分析) |

### 各阶段的输出标准

#### 前置规划 — HARA (Hazard Analysis and Risk Assessment)
```
safety-concept.md 至少包含：
├── Item Definition（系统的功能范围、边界、接口）
├── Hazard Identification（整车级危害识别）
├── Hazard Classification（S/E/C 评分 → ASIL）
├── Safety Goals（每条 Safety Goal = ASIL 等级）
└── FSC (Functional Safety Concept) 初步映射
```

#### Spec 阶段 — FSR (Functional Safety Requirements)
```
safety-requirements.md：
├── 每个 SHALL 需求标注 ASIL 等级 (QM/A/B/C/D)
├── 安全机制需求（如：过流检测 SHALL 在 100ms 内触发）
├── 故障响应时间约束（FTTI）
└── 安全状态定义
```

#### 架构阶段 — TSR (Technical Safety Requirements)
```
safety-architecture.md：
├── FTA (Fault Tree Analysis) — 顶层 Safety Goal → 底层故障
├── FMEA (Failure Mode & Effects Analysis) — 组件级故障
├── ASIL 分解（如果适用，如 ASIL-B(D)→QM(D)+ASIL-B(D)）
├── 安全机制设计（看门狗、ECC、双核锁步、CRC…）
├── 故障响应时间预算（FTTI 分解到各层）
└── Safety Case 初始版本
```

#### 审查阶段 — Safety Case
```
safety-review.md：
├── 安全机制覆盖检查
├── 安全异常分析（如果有偏离）
├── 安全测试覆盖率
├── 残余风险声明
└── 是否满足 ASIL 目标？
```

### 工具链集成

| 工具 | 用途 | 来源 |
|:-----|:-----|:-----|
| MISRA C:2012 检查器 | 代码静态分析 | yuleASR (自带 MISRA 报告) |
| 故障注入测试 | 验证安全机制 | 自研注入框架 |
| 覆盖率分析 | 结构覆盖率 | gcov/lcov |

---

## 🧩 新增：yuleASR BSW 集成流程

> **2026-06-27 新增** — BSW 不应该手写简化版，应该集成 yuleASR 的真实 BSW 模块。

### 集成步骤

每个项目在架构设计阶段，明确以下 yuleASR BSW 模块的选型：

#### 1. 通信栈
```
yuleASR 模块            代替手写版本
───────────────────────────────────────────
CanIf/Can               手写 CAN 模拟 → yuleASR CAN驱动
COM (Signal/I-PDU)      event_bus 简易发布 → COM 信号映射
PduR (PDU Router)       直接函数调用 → PDU 路由层
CanTp (传输协议)         无 → 诊断用传输层
```

#### 2. 诊断栈
```
yuleASR 模块            代替手写版本
───────────────────────────────────────────
DCM (Diagnostic Ctlr)   手写 diag.c → UDS 全协议栈
DEM (Diagnostic Evt Mgr) 手写 DTC FIFO → 完整 DTC 管理
FIM (Function Inhibit Mgr) 无 → 故障降级管理
```

#### 3. 存储栈
```
yuleASR 模块            代替手写版本
───────────────────────────────────────────
NvM (NVRAM Manager)     手写 storage.c → NvM 块管理
Fee (Flash EEPROM Emul.) 手写模拟 → 真实 Flash 模拟
MemIf (Memory If)        无 → 存储抽象层
```

#### 4. 系统服务
```
yuleASR 模块            代替手写版本
───────────────────────────────────────────
OS (OSEK AUTOSAR OS)    手写 scheduler.c → 抢占式 OS
EcuM (ECU Manager)      手写 power.c → 完整 ECU 状态机
BswM (BSW Manager)       无 → 模式管理
WdgM (Watchdog Mgr)      手写 hal_watchdog → 完整看门狗
```

#### 5. 安全服务
```
yuleASR 模块            用途
───────────────────────────────────────────
CSM (Crypto Service Mgr) 密钥管理 + 加解密
SecOC                    安全 CAN 报文
Crypto Driver (mbedTLS)  底层加密实现
```

### 集成到 CMake 中的方式

```cmake
# 添加 yuleASR 子目录
add_subdirectory(${YULEASR_PATH}/src/autosar/mcal)
add_subdirectory(${YULEASR_PATH}/src/autosar/ecual)
add_subdirectory(${YULEASR_PATH}/src/autosar/services)

# 仅需要手写的部分
add_library(scm_swc
    src/seat_adjust.c
    src/seat_heating.c
    src/seat_memory.c
    # ... 其他 SWC
)

target_link_libraries(scm_swc PRIVATE yuleasr_com yuleasr_dcm yuleasr_nvm)
```

---

## 核心理念

1. **OpenSpec** — 需求驱动，事事有规范。每个任务从 Spec 开始，用 SHALL 语句定义需求，GIVEN/WHEN/THEN 定义场景。变更必须伴随 spec delta。
2. **Superpowers** — 每个任务从 Superpowers 框架启动，逐步深入。回答 "为什么做、怎么做、优先级是什么"。14 Rules 全程生效。
3. **Harness Engineering** — agents 像流水线工位一样串联，每个步骤的输出自动成为下一步的输入。自动流转，零通知。
4. **CI/CD 三层流水线** — 开发验证(Layer1) → 集成验证(Layer2) → 系统验证(Layer3)，每层对应 ASPICE 不同过程域。
5. **Zero-notification** — 不打扰老板，只看最终报告。

## 三位一体职责分工

| 框架 | 回答的问题 | 产出物 | 负责人 |
|------|-----------|--------|--------|
| **OpenSpec** | 做什么？需求是什么？验收标准？ | `spec-contract.md` + `spec-delta.md` | 小马 🐴 |
| **Superpowers** | 为什么做？怎么做？优先做什么？ | `startup-analysis.md` + 14 Rules | 小明 🧑‍💼 |
| **Harness Engineering** | 谁来做？怎么流转？ | Pipeline + CI/CD + 自动化 | 小明 🧑‍💼 |

## Agents 流水线 v2.0

```
老板下达任务
   │
   ▼
╔═══════════════════════════════════════════════════════════╗
║                   小明 (Orchestrator / PM)                 ║
║  - 需求入口 + Superpowers 启动分析                       ║
║  - Agents 编排调度                                       ║
║  - 三线终审（业务价值维度）                              ║
║  - 争议裁决（小克🆚小马）                               ║
║  - Git 操作 + 最终报告                                   ║
╚═══════════════════════════════════════════════════════════╝
   │
   ├─→ 小马 🐴  : Spec 契约层 + 验收矩阵
   │       │
   │       ├─→ 小克 👨‍💻: 架构设计 → 小马审查架构
   │       │
   │       ├─→ 小克 👨‍💻: 开发 + check list 自测
   │       │       │
   │       │       └── 小马: 持续跟进（非正式审查）
   │       │
   │       ├─→ 小马 🐴  : 正式审查（规范对齐 + 可测试性）
   │       │
   │       ├─→ 小明 🧑‍💼: 终审（业务价值维度）
   │       │
   │       └─→ 小克: tech-debt.md + 根因分析
   │
   └──→ 小明: 最终报告 → 老板 ✅
```

### 三线确认机制

| 线 | 责任人 | 审查维度 |
|----|--------|----------|
| 第1线 | 小马 🐴 | 规范对齐 — 代码做的和 spec 说的一致吗？ |
| 第2线 | 小明 🧑‍💼 | 业务价值 — 实现解决了业务问题吗？边界覆盖了吗？ |
| 第3线 | 小克+小马 | 变更影响 — 这次改动波及了什么？需要更新其他 spec 吗？ |

## ASPICE V-Model + CI/CD 三层流水线

在 Agent 流水线之上，叠加嵌入式 CI/CD 验证层：

```
                    ASPICE Level
                    ┌────────────────────────────┐
                    │                            │
SWE.4/SYS.4 ◄──── Layer 1: 开发验证 CI         │
                    │  (每个 Commit: 单元测试      │
                    │   + 覆盖率门禁 + 风格检查)   │
                    ├────────────────────────────┤
SWE.5 ◄────────── Layer 2: 集成验证 CI          │
                    │  (MR: 交叉编译 + 静态分析    │
                    │   + 集成测试 + 全量审查)    │
                    ├────────────────────────────┤
SYS.5/SYS.6 ◄──── Layer 3: 系统验证 CD          │
                    │  (Release: E2E + 耐久测试   │
                    │   + 固件签名 + 证据链产出)  │
                    └────────────────────────────┘
```

每次 Release 自动产出 ASPICE 审计证据包：
```
evidence/
├── traceability-matrix.md    # 需求↔设计↔代码↔测试
├── review-log.json           # 所有 Agent 审查记录
├── test-coverage-report.md   # 代码覆盖率
├── requirement-coverage.md   # 需求覆盖率
└── compliance-pack.zip       # 一键导出给审计
```

## 15步自动化流程（融合量产前置 + OpenSpec + Superpowers + Harness Engineering）

```
[P0a] 小明 🧑‍💼: 量产就绪检查 ⭐ NEW
     ├─ 执行「量产就绪检查清单」
     ├─ 问老板: MCU 平台? ASIL 目标? yuleASR BSW 选型?
     ├─ 输出: project-context.md（含硬件/BSW/安全决策）
     └─ → 确认后进入正式流水线

[P0b] 小明 🧑‍💼: ISO 26262 HARA + Safety Goals ⭐ NEW
     ├─ 基于 project-context.md 做 HARA
     ├─ 识别整车级 Hazard → S/E/C 评分 → ASIL
     ├─ 输出 Safety Goals（每个带 ASIL 等级）
     ├─ 输出: safety-concept.md
     └─ → Safety Goals 并入 Spec

[P0] 小明 🧑‍💼: OpenSpec 需求启动
     ├─ 根据任务描述，确认是否有明确的需求规范
     ├─ 如果没有 → 安排 小马 🐴 写 spec-contract.md
     ├─ 如果有 → 验证需求完整性
     ├─ 格式: SHALL 语句 + GIVEN/WHEN/THEN 场景
     └─ → 输出 spec-contract.md（小马 🐴）

[P1] 小明: Superpowers 启动分析
     ├─ S(ituation) - 任务场景理解
     ├─ U(nderstanding) - 深层需求
     ├─ P(roblem) - 核心问题定义
     ├─ E(xecution) - 执行方案初步
     ├─ R(esources) - 资源评估
     ├─ P(riority) - 优先级判断
     └─ → 输出 startup-analysis.md

[P2] 小明 → 小马 🐴: Spec 契约层 + 验收矩阵
     ├─ 传递: spec.md + startup-analysis.md
     ├─ 输出: spec-contract.md（仅契约层，SHALL/SHOULD/MAY + 场景）
     ├─ 同步产出: acceptance-matrix.md（验收判定矩阵）
     └─ 注: 不再输出独立 PRD，PRD 内容合并为 spec 序言章节

[P3] 小明: 需求确认
     ├─ 确认 spec-contract.md 覆盖了 startup-analysis 的核心结论
     ├─ 一致 → 通过
     └─ 不一致 → 自动退回 + 备注原因

[P4] 小明: 排期规划
     ├─ 输出: schedule.md
     └─ → 自动流转

[P5] 小明 → 小克 👨‍💻: 架构设计
     ├─ 传递: spec-contract.md + acceptance-matrix.md + schedule.md
     ├─ 架构师确保设计满足 spec 所有 SHALL 语句
     ├─ 输出: architecture.md（含 SHALL 追溯表）
     └─ → 小马审查

[P5.5] 小马 🐴 → 小克: 架构审查（前置）
     ├─ 对照 spec 检查架构覆盖度
     ├─ 检查关键约束（性能、部署、接口协议）是否体现
     ├─ 通过 → 继续
     └─ 退回 → 带修改意见返小克

[P5.6] 小明 🧑‍💼: ISO 26262 TSR + 安全架构 ⭐ NEW
     ├─ 基于 architecture.md 导出 TSR（技术安全需求）
     ├─ FTA: Safety Goal → 底层故障树
     ├─ FMEA: 模块级故障模式 × 影响 × 检测
     ├─ ASIL 分解（如需：ASIL-B(D)=QM(D)+ASIL-B(D)）
     ├─ 安全机制设计（看门狗/ECC/双核锁步/CRC/EDAC）
     ├─ FTTI 分解到各模块
     ├─ 输出: safety-architecture.md
     └─ → 并入 architecture.md

[P6] 小克 👨‍💻: 开发
     ├─ 传递: architecture.md + spec-contract.md
     ├─ 每个功能点对应 spec 中的需求
     ├─ 输出: src/ 代码
     └─ → 小马持续跟进（非正式审查，随时走读关键模块）

[P7] 小克 👨‍💻: 自测
     ├─ 基于 spec SHALL 编写精简 check list
     ├─ 每条 SHALL 对应 1-2 个关键检查点
     ├─ 不写完整 GIVEN/WHEN/THEN 文档
     ├─ 输出: self-checklist.md
     └─ → 执行验证

[P7.5] 小克 👨‍💻: yuleASR BSW 集成 ⭐ NEW
     ├─ 基于架构设计的选择，集成 yuleASR 的 BSW 模块
     ├─ 通信栈: CanIf → COM → PduR
     ├─ 诊断栈: DCM → DEM
     ├─ 存储栈: NvM → Fee
     ├─ 系统服务: OS → EcuM → WdgM
     ├─ CMake: add_subdirectory(yuleASR/...)
     ├─ 将手写版本逐步替换为 yuleASR 真实 BSW
     └─ → 进入功能自测

[P8] 小马 🐴: 正式审查（含安全审查 ⭐）
     ├─ 传递: src/ + self-checklist.md + spec-contract.md
     ├─ 维度1: 规范对齐 — 代码实现了 spec 说的吗？
     ├─ 维度2: 可测试性 — 这个实现容易被验证吗？
     ├─ 维度3: 安全审查 ⭐ NEW — 安全机制覆盖？FTA 叶子覆盖？
     ├─ 输出: code-review.md + safety-review.md
     └─ → 小明

[P9] 小明 🧑‍💼: 三线终审（业务价值维度）
     ├─ 这个实现解决了业务问题吗？
     ├─ 边界覆盖了吗？
     ├─ 通过 → 继续
     └─ 退回 → 带 review 意见返小克

[P10] 小克 👨‍💻: 技术债务 + 根因分析
     ├─ 记录本次开发中发现的技术债务 → tech-debt.md
     ├─ 记录测试失败的根因分析 → rca-log.md
     ├─ 输出技术设计记录 → tech-notes.md（ADR 精简版）
     └─ → 小明

[P11] 小克 👨‍💻: 自动化覆盖率工具执行
     ├─ 运行覆盖率工具，验证 self-checklist 通过率
     ├─ 输出: test-coverage-report.md
     └─ → 小明

[P12] 小明 🧑‍💼: 证据汇总 + 上传仓库
     ├─ 汇总: architecture.md / src/ / self-checklist.md / code-review.md / tech-notes.md
     ├─ git commit + push
     └─ → 自动流转

[P13] 小明 🧑‍💼: 生成最终报告
     ├─ 综合所有步骤日志和证据
     ├─ 报告标题含 spec 版本号
     ├─ 格式: task-summary.md
     └─ → 发给老板 🎯
```

## 角色定义

| Agent | 工作 | 工具链 |
|-------|------|--------|
| **小明** 🧑‍💼 | 需求入口+Superpowers分析、编排、三线终审(业务价值)、争议裁决、git、报告 | `project-manager` |
| **小马** 🐴 | Spec契约层+验收矩阵、架构审查(前置)、代码审查(规范对齐+可测试性)、变更影响分析 | `hermes-agent` |
| **小克** 👨‍💻 | 架构设计(需小马审查)、开发、自测check list、技术债务跟踪、覆盖率工具、根因分析 | `claude-agent` |

### 小马 🐴 详细职责

**做：**
- Spec 契约层撰写（SHALL/SHALL NOT + GIVEN/WHEN/THEN）— 不可变，变更需全员同意
- 验收判定矩阵（同步产出）
- 架构设计审查（前置 — 小克做完架构后先给小马过）
- 代码审查（规范对齐维度 + 可测试性维度）
- 变更影响分析

**不做：**
- PRD 独立文档（合并为 Spec 序言章节）
- 逐字排版和语法格式化（工具化/精简）
- 微小频繁变更的逐次记录（累积到阈值再更新契约层）

### 小克 👨‍💻 详细职责

**做：**
- 架构设计（输出 architecture.md，含 spec→架构 SHALL 追溯表）
- 开发（src/）
- 自测 check list（精简验证项，非完整 GIVEN/WHEN/THEN）
- 技术债务跟踪（tech-debt.md）
- 覆盖率自动化工具
- 根因分析（RCA，测试失败后）
- 技术设计记录（tech-notes.md，含 ADR 精简版）

**不做：**
- 大量重复的格式化测试文档撰写
- 在缺少关键 spec 信息的情况下做架构决策（可打回要求补全）

### 小明 🧑‍💼 详细职责

**做：**
- 需求入口 + Superpowers S.U.P.E.R 启动分析
- Agents 编排调度
- 三线终审（业务价值维度 — 这个实现解决了问题吗？边界覆盖了吗？）
- 争议裁决（小克 vs 小马 分歧时的最终决策）
- Git 操作
- 最终报告

**不做：**
- 逐层内部评审（由小马前置审查替代）

## 命令

```bash
# 新任务，一键启动
project-manager init "功能名" "需求描述"

# 推进到下一步（小明代劳）
project-manager step <任务名> next

# 查看完整状态
project-manager status <任务名>

# 列出所有任务
project-manager list
```

## 六个必问自检（每轮执行前自查）

1. **有 spec 吗？** → OpenSpec SHALL/SHOULD/MAY 完整？
2. **有 spec-delta 吗？** → 变更是否已更新需求？
3. **有 S.U.P.E.R 分析吗？** → 知道为什么做、优先级？
4. **Task 有 Worktree 隔离吗？** → 不会污染其他工作区？
5. **有测试吗？** → 对应 spec 中的 GIVEN/WHEN/THEN？
6. **Agent 审查过了吗？** → 谁审的、结论是什么？

## 附录

### 三位一体对比

```
OpenSpec        →  "做什么"  →  Spec（需求的定义）
Superpowers     →  "为什么/怎么做"  →  分析（决策的依据）+ Rules（质量的铁规）
Harness Eng.    →  "谁来做/怎么流转"  →  流水线（执行的保障）+ CI/CD（交付的门禁）

缺一不可：
- 只有 Spec 没有分析 → 可能做错事
- 只有分析没有 Spec → 需求不精确
- 只有流水线没有前两者 → 高效地做无用功
- 没有 CI/CD → 做完没人验证
```

### 相关技能

- `osh-fusion` — 三位一体完整技能（含需求管理 + 工程化 + CI/CD 三层流水线）
- `ralph-loop` — 自主任务循环（无人在回路中）

### OpenSpec 快速参考

详细指南见 [`openspec-guide.md`](./openspec-guide.md)

```
## Requirement: <需求名>
- The system SHALL <必须功能>
- The system SHOULD <建议功能>
- The system MAY <可选功能>

## Scenario: <场景名>
- GIVEN <前置条件>
- WHEN <触发事件>
- THEN <预期结果>

## Spec Delta
- The system SHALL <原需求>
+ The system SHALL <新需求>
```

---

## 🔗 mattpocock/skills 整合（2026-08-04，老板确认）

> 来源: github.com/mattpocock/skills（41 技能已安装至 ~/.agents/skills/）
> 原则: 取其长处，补 yuleOSH 短板，不重复造轮子

### 整合矩阵（核心 5 项）

| 技能 | yuleOSH 环节 | 整合方式 | 状态 |
|------|-------------|---------|------|
| **code-review 双轴** | 小马复验（审查） | 复验升级为双轴并行：Standards 轴（代码规范 + Fowler smells，repo 标准优先）+ Spec 轴（对照 acceptance-matrix/PRD）；双轴独立 sub-agent 不污染上下文，聚合报告 | ✅ 已启用 |
| **diagnosing-bugs 循环** | 缺陷修复（Loop 1） | 固化「复现→最小化→3-5 假设排序→插桩→修复→回归」；**无 tight pass/fail 信号不假设**（红信号优先于读码理论） | ✅ 已启用（CI 修复即时应用） |
| **tdd 红绿重构** | 小克开发 | 垂直切片驱动，每个 slice 先红后绿，验收矩阵同步演进 | 📋 试点 |
| **grill-me 决策拷问** | 小马契约前 | spec 草案先 grill 决策树，穷尽分支再定稿（减少待裁决积压） | 📋 试点 |
| **to-spec→to-tickets→implement** | 需求流转 | 与 OpenSpec 融合：对话→spec→tickets（含阻塞边）→实现 | 📋 试点 |

### 双轴 code-review 执行要点（小马复验必读）

1. **固定点**：明确 diff 基准（commit/branch/tag/merge-base）
2. **Standards 轴**：repo 文档标准（CODING_STANDARDS/CONTRIBUTING）+ Fowler smell 基线（_Refactoring_ ch.3）；repo 标准覆盖基线；每个 smell 是标注启发式非硬违规
3. **Spec 轴**：对照 originating spec/issue/PRD；无 spec 则跳过并注明
4. **并行 sub-agent**：两轴独立跑，互不污染上下文，最后聚合

### diagnosing-bugs 纪律（小克/小马修 bug 必读）

1. **Phase 1 红信号优先**：先建 tight pass/fail 命令（对目标 bug 会红）；没有就停下说明，向老板要环境/工件/插桩许可，**不读码猜因**
2. **Phase 2 复现+最小化**：minimal repro 缩小假设空间，成为 Phase 5 回归测试
3. **Phase 3 假设**：生成 3-5 个排序假设再测，禁止单假设锚定
4. **Phase 4 插桩**：用 instrumentation 验证假设
5. **Phase 5 修复+回归**：修复后回归测试锁定

### 工具入口

- `~/.agents/skills/code-review/SKILL.md` / `diagnosing-bugs/SKILL.md` / `tdd/SKILL.md` / `grilling/SKILL.md` / `to-spec/SKILL.md`
- yuleOSH 仓库 `docs/` 可沉淀为 CODING_STANDARDS.md（双轴 Standards 轴数据源）
