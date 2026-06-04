---
name: osh-fusion
description: "OpenSpec + Superpowers + Harness Engineering 三位一体融合方法论。从需求管理到工程化全流程，专为嵌入式 ASPICE 开发平台设计。"
metadata:
  version: 1.0.0
  author: 小明
  created: 2026-06-04
---

# OSH-Fusion — OpenSpec + Superpowers + Harness Engineering

三位一体融合：**O**penSpec（做什么）→ **S**uperpowers（为什么/怎么做）→ **H**arness Engineering（谁来做/怎么流转）。

## 🧠 核心理念

```
没有 Spec 就没有方向     →  OpenSpec 提供需求精确定义
没有 Rules 就没有质量    →  Superpowers 提供规则引擎门禁
没有 Pipeline 就没有效率  →  Harness Engineering 提供自动流水线
三者缺一不可
```

## 🎯 适用场景

- 嵌入式开发全流程（需求→设计→编码→测试→CI/CD）
- ASPICE V-Model 合规项目（SYS.3 → SWE.6）
- 敏捷迭代 + 合规并行的混合模式
- 需要全链路 Agent 自动审查的项目

---

## 📐 架构总览：OSS Pipeline

```
                    ┌──────────────────────────┐
                    │    OpenSpec Layer         │ ← 需求定义层
                    │   spec.md + spec-delta.md  │
                    └──────────┬───────────────┘
                               │ SHALL/SHOULD/MAY 语句
                               ▼
                    ┌──────────────────────────┐
                    │   Superpowers Layer        │ ← 规则引擎层
                    │   14 Rules + Agent 审查    │
                    └──────────┬───────────────┘
                               │ 门禁/审查结果
                               ▼
                    ┌──────────────────────────┐
                    │ Harness Engineering Layer │ ← 调度执行层
                    │    Agent Pipeline + CI/CD  │
                    └──────────────────────────┘
```

---

## 📋 第一阶段：需求管理（OpenSpec-driven）

### 规范格式（严格的 RFC 2119）

```markdown
## Requirement: <需求名称>

- The system SHALL <必须功能>
- The system SHOULD <建议功能>  
- The system MAY <可选功能>

## Reason
<为什么有这个需求>

## Scenario: <场景名>
- GIVEN <前置条件>
- WHEN <触发事件>
- THEN <预期结果>
- AND <附加结果>

## Acceptance Criteria
<可量化的通过条件>
```

### 需求变更管理 — Spec Delta

```markdown
## Requirement: <需求名称>

- The system SHALL <原需求>
+ The system SHALL <新需求>

## Scenario: <场景名称>
- GIVEN <原条件>
+ GIVEN <新条件>
```

### 需求层级结构（ASPICE 对齐）

```
SYS.3 ── 系统需求
  ├── Req-SYS-001 系统功能需求
  ├── Req-SYS-002 系统安全需求
  └── Req-SYS-003 系统接口需求
       │
       ▼
SWE.1 ── 软件需求
  ├── Req-SW-001 软件功能需求
  ├── Req-SW-002 软件性能需求
  └── Req-SW-003 软件安全需求
       │
       ▼
SWE.2 ── 软件架构设计 (DDD 限界上下文)
SWE.3 ── 软件详细设计 (Task 分解)
SWE.4 ── 单元测试 (TDD)
SWE.5 ── 集成测试
SWE.6 ── 软件合格性测试
SYS.5 ── 系统集成
SYS.6 ── 系统合格性
```

### S.U.P.E.R 启动分析框架

每个需求开始前必须做：

```
S — Situation    场景理解：当前状态、上下文、约束
U — Understanding 深层需求：真正的痛点是什么
P — Problem      核心问题：定义要解决的精确问题
E — Execution    执行方案：初步思路、技术选型方向
R — Resources    资源评估：人力、时间、工具、依赖
```

---

## 🔧 第二阶段：工程化过程（Superpowers + Harness）

### SDD → DDD → TDD 三阶段流水线

#### 阶段 1：SDD（Spec-Driven Development）

```
输入: spec.md + startup-analysis.md
输出: design-doc.md (限界上下文 + 聚合根 + 实体/值对象)
Rules: architecture:general, domain:modeling, code:style

执行:
1. 检查 spec 格式完整性 (SHALL+GIVEN/WHEN/THEN 全覆盖)
2. PLAN-LINT: kind 分类 + T00 三段法校验
3. 架构设计：限界上下文划分、聚合根识别
4. 设计文档输出到 docs/specs/YYYY-MM-DD-topic-design.md
```

#### 阶段 2：DDD（Domain-Driven Design & Planning）

```
输入: design-doc.md
输出: Task 分解 + Worktree 隔离
Rules: domain:m o d e l i n g, architecture:general

执行:
1. Worktree 隔离判定（C1:tasks≥2 | C2:files≥2 | C5:feature/bugfix）
2. Task 分解：kind 分类 (feature/bugfix/refactor/docs-config)
3. 每个 Task 绑定对应 spec 需求（可追溯）
4. T00 三步法模板强制执行
```

#### 阶段 3：TDD（Test-Driven Development）

```
RED    ── 写失败测试（对应 spec 场景）→ run test → FAIL 证据
GREEN  ── 最小实现通过 → run test → PASS 证据
REFACTOR ── 坏味道检测 → 重构 → 全测试仍绿

Gate: per-task auto-reviewer（路径映射 → Agent 组合）
       pass → commit | fail → 打包重试（最多 5 轮）
```

---

## 🚀 第三阶段：CI/CD 三层流水线（Harness Engineering）

### Layer 1：开发验证 CI（每个 Commit → SWE.4 覆盖）

```
[Commit Hook]
  ├── pre-commit: plan-lint + code-style + clang-tidy
  ├── 单元测试: Unity/CUnit/GTest + 覆盖率门禁(>80% line, >98% cond)
  ├── per-task auto-reviewer 并行触发
  │   ├── architecture-general agent
  │   ├── domain-modeling agent
  │   └── code-style agent
  └── evidence: test-report.md + coverage-report.md
```

### Layer 2：集成验证 CI（Merge Request → SWE.5 覆盖）

```
[MR Pipeline]
  ├── 全量编译（交叉编译链矩阵）
  │   ├── ARM GCC / RISC-V GCC / x86_64(Host 仿真)
  │   └── 固件体积门禁 (ROM/RAM 预算)
  ├── 静态分析
  │   ├── MISRA-C/C++ 规则检查
  │   ├── AUTOSAR 规则检查（按需）
  │   └── 圈复杂度 ≤ 15
  ├── 集成测试
  │   ├── API 契约测试
  │   ├── 组件交互测试
  │   └── 内存安全检测 (Valgrind / ASan)
  ├── /code-review all（全量 Agent 审查）
  │   ├── coverage-guardian（覆盖率门禁）
  │   ├── architecture-reviewer（架构一致性）
  │   └── security-reviewer（安全审计）
  └── evidence: integration-test-report.md + review-summary.json
```

### Layer 3：系统验证 CD（Release Tag → SYS.5/SYS.6 覆盖）

```
[Release Pipeline]
  ├── 系统级测试
  │   ├── 端到端场景测试（匹配 spec 中所有场景）
  │   ├── 压力测试 / 耐久测试 (24h+)
  │   ├── 实时性分析 (最差响应时间/FPS)
  │   └── 边界条件/模糊测试
  ├── ASPICE 证据链自动生成（核心价值）
  │   ├── 追溯矩阵 (Req→Design→Impl→Test)
  │   ├── 覆盖率报告（需求覆盖率 + 代码覆盖率）
  │   ├── 评审记录汇总（所有 Agent review JSON）
  │   └── 合规证书 / 审计包导出
  ├── 固件构建与发布
  │   ├── 生产固件签名
  │   ├── OTA 包生成
  │   └── 版本管理（SemVer + Commit SHA）
  └── evidence: release-report.md + compliance-pack.zip
```

---

## 👥 Agent 角色职责矩阵

| 阶段 | 小明 (PM/Orchestrator) | Hermes (产品/审查) | Claude (架构/开发) |
|:----|:----------------------|:-----------------|:-----------------|
| 需求 | OpenSpec 合规检查 | 写 spec.md + prd.md | — |
| 分析 | S.U.P.E.R 启动分析 + 排期 | 需求评审 | — |
| 设计 | Worktree 分配 + 监督 | — | 架构设计 + 领域建模 |
| 开发 | 进度跟踪 | — | 编码 + 自测 |
| TDD | 验证证据 | — | RED→GREEN→REFACTOR |
| 审查 | 内部评审汇总 | 代码 Agent 审查 | — |
| CI/CD | Pipeline 编排 + 报告 | 审查 AGent | — |

---

## 📂 项目结构标准

```
project/
├── specs/                     # OpenSpec 需求规范（源）
│   ├── sys-reqs.md            # 系统需求 (SYS.3)
│   ├── sw-reqs.md             # 软件需求 (SWE.1)
│   └── spec-delta/            # 变更 delta 追踪
├── openspec/                  # OpenSpec CLI 结构
│   ├── config.yaml
│   ├── specs/
│   ├── changes/
│   └── schemas/
├── docs/
│   ├── architecture.md        # 架构设计 (SWE.2)
│   ├── design-details.md      # 详细设计 (SWE.3)
│   └── adr/                   # 架构决策记录
├── tasks/                     # Task 管理
│   └── {task-name}/
│       ├── spec.md
│       ├── tasks.md
│       └── log/
├── src/                       # 源代码
├── test/                      # 测试代码
│   ├── unit/                  # 单元测试 (SWE.4)
│   ├── integration/           # 集成测试 (SWE.5)
│   └── system/                # 系统测试 (SYS.5/SYS.6)
├── ci/                        # CI/CD 配置
│   ├── dev-verify.yaml        # Layer 1
│   ├── int-verify.yaml        # Layer 2
│   └── sys-verify.yaml        # Layer 3
└── evidence/                  # ASPICE 证据
    ├── traceability-matrix.md
    ├── review-log.json
    └── compliance-pack/
```

---

## 💡 触发短语

当用户提到以下关键词时加载本技能：

- "OpenSpec" + "Superpowers" + 任意工程话题
- "三位一体" / "融合方法论"
- "嵌入式开发平台" / "嵌入式 SaaS"
- "ASPICE V-Model" / "ASPICE 合规"
- "全自动开发到测试"
- "需求管理 + 工程化" / "需求管理平台"
- "自托管全流程"

---

## 📎 参考文档

- [OpenSpec 快速参考](../sop/openspec-guide.md)
- [Harness Engineering SOP](../sop/project-workflow.md)
- [Superpowers 工作流编排图](./references/superpowers-flow.md)
