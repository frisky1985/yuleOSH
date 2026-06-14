# ASPICE 工具认证评估框架 — ASPICE Readiness Assessment

> **版本**: v1.0.0 | **状态**: DRAFT  
> **维护人**: 小马 🐴 (质量架构师)  
> **参考标准**: ASPICE 4.0 (PAM) / ISO 26262-8:2018 §8 / ISO 26262-6:2018 §6  
> **最后更新**: 2026-06-14

---

## 1. 概述

### 1.1 目的

本文档对 yuleOSH 进行 **ASPICE（Automotive Software Process Improvement and Capability Determination）工具认证评估**。主要目标：

1. **评估差距** — 对照 ASPICE 4.0 要求，识别 yuleOSH 当前的合规差距。
2. **路线图** — 制定从当前状态到 ASPICE AL2（Assessment Level 2）的里程碑计划。
3. **工具置信度** — 满足 ISO 26262-8 §8 对软件工具的置信度要求。

### 1.2 范围

本文档评估的范围：

- **ASPICE 4.0 过程域**：SYS.1-SYS.5, SWE.1-SWE.6, SUP.1-SUP.10, ACQ.4
- **工具链认证**：yuleOSH 自身及其使用的所有工具
- **评估对象**：yuleOSH v1.0.0 代码库、文档、CI pipeline、测试套件

### 1.3 参考标准

| 标准 | 节/条款 | 相关性 |
|:-----|:--------|:-------|
| ASPICE 4.0 | SWE.4 — 软件测试验证 | yuleOSH 测试覆盖规范和 RTM |
| ASPICE 4.0 | SWE.5 — 软件集成与测试 | CI pipeline 层级验证 |
| ASPICE 4.0 | SWE.6 — 软件确认与发布 | Release 门禁 |
| ASPICE 4.0 | SYS.5 — 系统集成与测试 | HIL / E2E 测试 |
| ASPICE 4.0 | SUP.9 — 变更与配置管理 | spec-delta + CI 配置 |
| ISO 26262-8:2018 | §8 — 软件工具认证 | 工具分类 / TCL / 置信度 |
| ISO 26262-6:2018 | §6 — 软件单元测试 | 测试方法、覆盖率要求 |
| ISO 26262-6:2018 | §10 — 软件集成测试 | 测试规范要求 |

### 1.4 术语定义

| 术语 | 定义 |
|:----|:-----|
| **ASPICE** | Automotive SPICE — 汽车行业软件过程改进和能力评估模型 |
| **AL** | Assessment Level — ASPICE 评估等级（AL1=已执行, AL2=已管理, AL3=已建立） |
| **TCL** | Tool Confidence Level — ISO 26262-8 §8 工具置信度等级（TCL1/TCL2/TCL3） |
| **TI** | Tool Impact — 工具对安全目标的潜在影响 |
| **PAM** | Process Assessment Model — ASPICE 过程评估模型 |
| **BP** | Base Practice — ASPICE PAM 中的基础实践 |
| **GP** | Generic Practice — ASPICE 通用实践 |
| **HIL** | Hardware-in-the-Loop — 硬件在环测试 |
| **SIL** | Software-in-the-Loop — 软件在环测试（QEMU 仿真） |

---

## 2. ASPICE 4.0 对工具认证的要求

### 2.1 相关过程域

ASPICE 4.0 中与 yuleOSH 工具能力直接相关的过程域：

| 过程域 | 编号 | 相关 BP/GP | yuleOSH 对应组件 |
|:-------|:----:|:-----------|:------------------|
| 软件需求分析 | SWE.1 | BP1-BP6 | `src/yuleosh/spec/` — OpenSpec 需求引擎 |
| 软件架构设计 | SWE.2 | BP1-BP5 | `src/yuleosh/ci/` — CI 架构 |
| 软件详细设计 | SWE.3 | BP1-BP6 | `docs/design/` — 设计文档 |
| 软件单元验证 | SWE.4 | BP1-BP5 | 测试套件 + RTM |
| 软件集成与集成测试 | SWE.5 | BP1-BP8 | CI pipeline L1→L3 |
| 软件确认与发布 | SWE.6 | BP1-BP6 | Release 门禁 + Evidence Pack |
| 系统需求分析 | SYS.1 | BP1-BP5 | `docs/spec.md` — 系统需求 |
| 系统架构设计 | SYS.2 | BP2-BP3 | 硬件 + 软件架构 |
| 变更管理 | SUP.9 | BP1-BP4 | spec-delta + git 变更追踪 |
| 配置管理 | SUP.10 | BP1-BP3 | 版本控制 + CI 产物管理 |

### 2.2 ISO 26262-8 §8 工具认证要求

ISO 26262-8 §8 要求对开发安全相关系统所用工具进行分类和认证：

**步骤 1：工具影响评估（TI — Tool Impact）**

| TI 等级 | 描述 | 评估方法 |
|:-------:|:-----|:---------|
| TI1 | 工具故障不会引入错误或仅引入已检测的错误 | 无需额外置信度 |
| TI2 | 工具故障可能引入**未检测**的错误 | 需要工具置信度认证 |
| TI3 | 工具故障可能引入错误且**防止检测**错误 | 最高置信度要求 |

**步骤 2：工具置信度等级（TCL）**

| TCL | 要求 | 适用场景 |
|:---:|:-----|:---------|
| TCL1 | 开发流程经验证即可 | TI1 场景 |
| TCL2 | 需要工具验证措施 | TI2 场景，使用已知可靠的方法 |
| TCL3 | 需要严格工具验证 | TI2/TI3 场景，高风险 |

> 参考：ISO 26262-8:2018 §8.4.3 Table 1 — 工具分类矩阵

**步骤 3：工具认证方法**

ISO 26262-8 定义了三种工具认证方法：

- **方法 1**：工具开发流程的置信度（工具本身遵循功能安全流程开发）
- **方法 2**：工具验证措施的置信度（工具产生的结果可通过其他方式验证）
- **方法 3**：工具在上下文中使用的置信度（工具的使用方式降低了风险）

### 2.3 ASPICE 4.0 对工具链的评估等级

| 等级 | 名称 | 描述 | yuleOSH 当前状态 |
|:----:|:-----|:-----|:----------------:|
| AL0 | 不完整 | 过程未执行或未达到目标 | — |
| AL1 | 已执行 | 过程执行并产出工作产品 | ✅ 基本达成 |
| AL2 | 已管理 | 过程被规划、监控和调整 | 🟡 部分达成 |
| AL3 | 已建立 | 过程基于标准流程定制 | 🔴 部分达成 |

**yuleOSH 当前过程域成熟度概览：**

```
过程域         AL0   AL1   AL2   AL3
SWE.1 软件需求   ████████████░░  77%
SWE.2 架构设计   ██████████░░░░  66%
SWE.3 详细设计   █████████░░░░░  58%
SWE.4 单元测试   ██████████████  90%
SWE.5 集成测试   █████████████░░  78%
SWE.6 确认发布   ██████████░░░░  65%
SYS.1 系统需求   ████████████░░  80%
SUP.9 变更管理   █████████████░░  76%
SUP.10 配置管理  ██████████░░░░  64%
```

---

## 3. yuleOSH 当前差距分析

### 3.1 ASPICE SWE.4 — 软件单元验证

**已满足：**
- ✅ 单元测试覆盖（~62.3% 行覆盖率，部分模块 100%）
- ✅ pytest + coverage 工具链搭建
- ✅ 测试结果自动归档（JUnit XML + JSON）
- ✅ 测试通过率 100%（671 passed）
- ✅ store_pg.py 100% 行 + 分支覆盖

**差距：**

| 编号 | ASPICE 要求 | yuleOSH 差距 | 严重度 |
|:----|:------------|:-------------|:------:|
| SWE.4-BP1 | 制定软件单元验证规范，包括测试策略 | 已有文档但不完整（缺少形式化测试规范） | 🟡 中 |
| SWE.4-BP2 | 验证输入/输出的正确性 | 部分模块缺少输出边界值验证 | 🟡 中 |
| SWE.4-BP3 | 测试覆盖软件单元的功能和行为 | 行覆盖充分，但**分支覆盖**未跟踪 | 🔴 高 |
| SWE.4-BP4 | 验证软件单元的资源消耗 | ❌ 无资源消耗/性能测试 | 🔴 高 |
| SWE.4-BP5 | 使用统计方法验证正确性 | ❌ 无基于模型/统计的测试 | 🟡 中 |
| SWE.4-BP7 | 记录测试结果和追溯 | RTM 已定义但尚未 CI 集成（本文档配套） | 🟡 中 |

### 3.2 ASPICE SWE.5 — 软件集成与集成测试

**已满足：**
- ✅ 多层 CI pipeline（L1→L3）
- ✅ SIL（QEMU 仿真）集成
- ✅ HIL（硬件在环，mock 模式）
- ✅ 层间依赖验证

**差距：**

| 编号 | ASPICE 要求 | yuleOSH 差距 | 严重度 |
|:----|:------------|:-------------|:------:|
| SWE.5-BP2 | 定义集成策略 | 有 pipeline 层次但缺少正式集成策略文档 | 🟡 中 |
| SWE.5-BP3 | 验证接口一致性 | ❌ 无跨模块接口契约测试 | 🔴 高 |
| SWE.5-BP5 | 验证接口的数据一致性 | ❌ 无数据流/协议验证 | 🔴 高 |
| SWE.5-BP6 | 回归测试策略 | 有部署但无正式回归选择策略文档 | 🟡 中 |
| SWE.5-BP7 | 测试覆盖率评估 | 已有行覆盖；**需求覆盖（RTM）**未自动化 | 🟡 中 |

### 3.3 ASPICE SWE.6 — 软件确认与发布

**已满足：**
- ✅ Release 门禁已定义（覆盖率 >= 门禁值）
- ✅ Evidence Pack 收集

**差距：**

| 编号 | ASPICE 要求 | yuleOSH 差距 | 严重度 |
|:----|:------------|:-------------|:------:|
| SWE.6-BP1 | 制定确认测试规范 | ❌ 无独立的确认测试规范文档 | 🔴 高 |
| SWE.6-BP3 | 测试与实际运行环境的兼容性 | cross/*.py 测试覆盖不完整 | 🟡 中 |
| SWE.6-BP5 | 确认测试的独立性 | 无独立的确认团队或流程 | 🟡 中 |

### 3.4 ISO 26262-8 §8 工具认证差距

| 工具 | 功能 | TI 等级 | TCL 需求 | 当前状态 |
|:----|:-----|:-------:|:--------:|:---------|
| **yuleOSH CLI** | 生成、测试、打包 | TI2 | TCL2 | ❌ 未认证 |
| **pytest** | 测试执行 | TI2 | TCL2 | ✅ 广泛验证 |
| **OpenSpec 引擎** | 需求解析 | TI2 | TCL2 | 🟡 部分验证 |
| **CI Pipeline** | 自动化构建 | TI2 | TCL2 | 🟡 部分验证 |
| **Coverage 工具** | 覆盖率测量 | TI2 | TCL3 | 🟡 少量验证 |
| **Evidence Pack** | 合规证据 | TI1 | TCL1 | 🟡 部分验证 |
| **HIL Mock 模式** | 硬件仿真 | TI2 | TCL2 | ❌ 未认证 |
| **SIL (QEMU)** | 软件仿真 | TI2 | TCL2 | 🟡 部分验证 |

### 3.5 差距总览表

| 差距编号 | 类型 | 描述 | 优先级 | 影响的过程域 |
|:--------|:-----|:-----|:------:|:-------------|
| GAP-001 | 文档 | 缺少形式化 SWE.4 测试规范 | P0 | SWE.4 |
| GAP-002 | 工具 | 分支覆盖率未跟踪 | P0 | SWE.4 |
| GAP-003 | 文档 | 缺少集成策略文档 | P1 | SWE.5 |
| GAP-004 | 测试 | 无跨模块接口契约测试 | P1 | SWE.5 |
| GAP-005 | 文档 | 缺少确认测试规范 | P1 | SWE.6 |
| GAP-006 | 测试 | 无资源消耗/性能测试 | P1 | SWE.4 |
| GAP-007 | 自动化 | RTM CI 集成未完整实现 | P1 | SWE.4 |
| GAP-008 | 审计 | 工具置信度文档不完整 | P2 | ISO 26262-8 |
| GAP-009 | 平台 | cross/*.py 模块覆盖不足 | P2 | SWE.5 |
| GAP-010 | 流程 | 无正式回归测试选择策略 | P2 | SWE.5 |

---

## 4. 达标路线图和里程碑

### 4.1 总体路线图

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 路线图：yuleOSH ASPICE AL2 + ISO 26262-8 TCL2 达标计划                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  2026-Q2          2026-Q3              2026-Q4              2027-Q1    │
│  (当前)                                                                │
│    │                │                     │                    │        │
│    ▼                ▼                     ▼                    ▼        │
│ ┌──────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    │
│ │M0    │    │M1             │    │M2             │    │M3             │   │
│ │基线  │───→│测试体系完善    │───→│集成与确认完善   │───→│工具认证+审计   │   │
│ └──────┘    └──────────────┘    └──────────────┘    └──────────────┘    │
│                                                                         │
│  当前:        目标:              目标:               目标:               │
│  • AL1 部分   • AL1 全部达成     • SWE.5/6 AL2       • AL2 全量评估     │
│  • 覆盖率60%  • 覆盖率70%        • 覆盖率80%         • 覆盖率85%        │
│  • RTM 规范   • RTM CI 集成      • 接口契约测试      • 工具认证文档     │
│  • 无工具认证  • 分支覆盖跟踪     • 性能测试基准      • TCL2/TCL3 认证   │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 里程碑 M0 — 当前基线 (2026-Q2 已完成)

| 交付物 | 状态 | 对应的 ASPICE 域 |
|:-------|:----:|:----------------|
| RTM 规范 (`docs/rtm-spec.md`) | ✅ APPROVED | SWE.4 |
| 测试覆盖规范 (`docs/test-coverage-standards.md`) | ✅ APPROVED | SWE.4 |
| 覆盖率阶梯计划 (`docs/ci-coverage-gateway.md`) | ✅ DRAFT | SWE.4 / SUP.9 |
| RTM CI 集成规范 (`docs/rtm-ci-integration.md`) | ✅ DRAFT | SWE.4 |
| 贡献者测试指南 (`docs/contributor-testing-guide.md`) | ✅ DRAFT | SWE.4 |
| CI pipeline (L0→L3) | ✅ 运行中 | SWE.5 |
| 全量测试 671 passed | ✅ | SWE.4 |
| store_pg 100% 覆盖 | ✅ | SWE.4 |

### 4.3 里程碑 M1 — 测试体系完善 (2026-Q3)

**目标**：ASPICE SWE.4 全部 AL1，部分 AL2。

| # | 行动项 | 负责人 | 截止日 | 产出 |
|:--|:-------|:------|:------|:-----|
| M1-01 | 实现 RTM CI 集成（yuleosh rtm 命令） | 后端组 | Q3-W4 | `src/yuleosh/rtm/` 模块 |
| M1-02 | 实现分支覆盖跟踪 | CI 组 | Q3-W4 | CI 输出 branch coverage |
| M1-03 | 覆盖率阶梯 L1→L2 升级 | 质量架构师 | Q3-W6 | `pytest.ini` 更新到 70% |
| M1-04 | 编写 SWE.4 正式测试规范文档 | 质量架构师 | Q3-W4 | `docs/swe4-test-spec.md` |
| M1-05 | 补齐 cross/*.py 测试覆盖 | 后端组 | Q3-W6 | 500+ 新增测试 |
| M1-06 | 实现 SHALL 覆盖率 90% 门禁 | 后端组 | Q3-W8 | CI RTM 门禁生效 |
| M1-07 | 消除覆盖率债务 50% | 全组 | Q3-W8 | `coverage-debt.md` 减少 |

**验收标准：**

| 指标 | 目标 |
|:-----|:----|
| 行覆盖率 | ≥70% |
| 分支覆盖率 | ≥60%（首次跟踪） |
| RTM CI 门禁 | 运行中，SHALL 覆盖率 ≥90% |
| store_pg.py | 维持 ≥95% |
| ci/run.py | 维持 ≥80% |
| cross/*.py | ≥60% |
| ASPICE SWE.4 评估 | AL1 全部达成，AL2 ≥50% |

### 4.4 里程碑 M2 — 集成与确认完善 (2026-Q4)

**目标**：ASPICE SWE.5、SWE.6 全部 AL1，部分 AL2。

| # | 行动项 | 负责人 | 截止日 | 产出 |
|:--|:-------|:------|:------|:-----|
| M2-01 | 定义正式集成策略 | 架构评审 (老陈) | Q4-W2 | `docs/swe5-integration-strategy.md` |
| M2-02 | 实现跨模块接口契约测试 | 后端组 | Q4-W4 | `tests/test_contracts_*.py` |
| M2-03 | 实现回归测试自动选择 | CI 组 | Q4-W4 | `ci/regression-selector.py` |
| M2-04 | 编写 SWE.6 确认测试规范 | 质量架构师 | Q4-W4 | `docs/swe6-confirmation-spec.md` |
| M2-05 | 建立性能测试基准 | 后端组 | Q4-W6 | `tests/test_perf_*.py` |
| M2-06 | 覆盖率阶梯 L2→L3 升级 | 质量架构师 | Q4-W6 | `pytest.ini` 更新到 75% |
| M2-07 | 编写 HIL 测试认证文档 | 硬件组 | Q4-W8 | `docs/hil-qualification.md` |
| M2-08 | Release 门禁增强（RTM 95%） | CI 组 | Q4-W8 | Release pipeline |

**验收标准：**

| 指标 | 目标 |
|:-----|:----|
| 行覆盖率 | ≥75% |
| 分支覆盖率 | ≥65% |
| 接口契约测试 | 覆盖 top-10 接口 |
| 性能基准 | 基线建立，≤10% 降级告警 |
| Release RTM 门禁 | SHALL ≥95% |
| ASPICE SWE.5 评估 | AL1 全部达成，AL2 ≥40% |
| ASPICE SWE.6 评估 | AL1 全部达成 |

### 4.5 里程碑 M3 — 工具认证 + 最终审计 (2027-Q1)

**目标**：ASPICE AL2 全量评估，ISO 26262-8 TCL2 工具认证。

| # | 行动项 | 负责人 | 截止日 | 产出 |
|:--|:-------|:------|:------|:-----|
| M3-01 | yuleOSH CLI 工具置信度文档 | 质量架构师 | Q1-W4 | `docs/tool-qualification.md` |
| M3-02 | OpenSpec 引擎 TCL2 认证 | 后端组 | Q1-W4 | OpenSpec 验证套件 |
| M3-03 | Coverage 工具 TCL3 认证 | CI 组 | Q1-W6 | 双工具覆盖率交叉验证 |
| M3-04 | CI Pipeline TCL2 认证 | CI 组 | Q1-W6 | Pipeline 验证套件 |
| M3-05 | SIL (QEMU) 工具认证 | 硬件组 | Q1-W8 | `docs/sil-qualification.md` |
| M3-06 | 覆盖率阶梯 L4→L5 升级 | 质量架构师 | Q1-W8 | `pytest.ini` 更新到 85% |
| M3-07 | 内部 ASPICE AL2 模拟评估 | 质量架构师 | Q1-W10 | 评估报告 |
| M3-08 | 差距补救 | 全组 | Q1-W12 | 修复所有 AL2 阻塞项 |

**验收标准：**

| 指标 | 目标 |
|:-----|:----|
| 行覆盖率 | ≥85% |
| 分支覆盖率 | ≥75% |
| TCL2 认证工具 | yuleOSH CLI, OpenSpec, CI Pipeline |
| TCL3 认证工具 | Coverage 工具（双验证） |
| ASPICE SWE.4 AL2 | ≥80% 达成 |
| ASPICE SWE.5 AL2 | ≥70% 达成 |
| ASPICE SWE.6 AL2 | ≥60% 达成 |
| 无 AL0 过程域 | 全部 ≥AL1 |

---

## 5. 工具分类矩阵（ISO 26262-8）

### 5.1 yuleOSH 工具分类

| 工具名称 | 功能 | 可能故障 | TI | 建议 TCL | 认证方法 |
|:---------|:-----|:---------|:--:|:--------:|:--------|
| yuleosh CLI | 需求解析、测试执行、证据打包 | 错误解释 SHALL 语句 | TI2 | TCL2 | 方法 1+2 |
| pytest + coverage | 测试执行 + 覆盖率报告 | 错误统计遗漏行 | TI2 | TCL3 | 方法 2+3 |
| OpenSpec 引擎 | spec.md 解析 → 需求树 | 遗漏需求、错误 ID 分配 | TI2 | TCL2 | 方法 1+2 |
| CI Pipeline | 自动化构建 + 门禁 | 跳过阶段、错误归因 | TI2 | TCL2 | 方法 1+3 |
| SIL (QEMU) | 软件仿真 | 仿真行为与真实硬件不一致 | TI2 | TCL2 | 方法 2+3 |
| HIL Runner | 硬件在环测试 | 错误注入 / 错误读数 | TI2 | TCL2 | 方法 2+3 |
| Evidence Pack | 合规证据打包 | 遗漏文件、错误版本 | TI1 | TCL1 | 方法 1 |

### 5.2 TCL2 认证标准

对于 TCL2 工具，yuleOSH SHALL 提供以下证据：

```markdown
### 工具认证证据：OpenSpec 引擎

**工具**: yuleosh.spec.OpenSpecParser v1.0.0
**TCL**: TCL2
**TI**: TI2

**认证方法**: 方法 1（开发流程）+ 方法 2（验证措施）

**方法 1 证据：**
1. 工具开发遵循代码审查流程 ✅
2. 工具版本有 git tag + release notes ✅
3. 工具变更通过 PR + CI ✅
4. 工具有单元测试覆盖（当前 55% → 目标 70%）🔄

**方法 2 证据：**
1. RTM 追溯验证（spec→test 双向）✅
2. 人工审阅所有生成的 spec 输出 ✅
3. 与 reference parser 的输出对比测试 🔄

**剩余工作：**
- 增加 OpenSpec 解析的 Golden Test 套件（expect 文件对比）
- 将覆盖率提升到 70%
- 编写工具用户指南/API 文档
```

### 5.3 TCL3 认证标准（Coverage 工具）

覆盖工具需要更严格的验证：

```markdown
### 工具认证证据：pytest-cov v6.x

**工具**: pytest-cov (coverage.py Python 覆盖率测量工具)
**TCL**: TCL3
**TI**: TI2

**认证方法 2（双工具交叉验证）：**
- 同一份代码同时用 coverage.py 和 sloccount-cloc 测量
- 差异率 ≤ 2% 才可接受
- 每周自动化交叉验证

**认证方法 3（上下文使用降低风险）：**
- CI 中同时测量行覆盖和分支覆盖
- 门禁要求 ≥ 两个工具均在阈值以上
- 手动走查每个 Release 的覆盖率报告
```

---

## 6. ASPICE AL2 具体检查表

### 6.1 SWE.4 AL2 检查表

| # | GP 要求 | 证据 | 状态 | 负责人 |
|:--|:--------|:-----|:----:|:------|
| SWE.4-GP1 | 过程目标已定义 | `docs/test-coverage-standards.md` | ✅ | 小马 🐴 |
| SWE.4-GP2 | 过程输出已规划 | `docs/ci-coverage-gateway.md` | ✅ | 小马 🐴 |
| SWE.4-GP3 | 过程监控 | CI dashboard / 趋势跟踪 | 🟡 需增强 | CI 组 |
| SWE.4-GP4 | 过程调整 | 覆盖率阶梯升级/降级机制 | ✅ | 小马 🐴 |
| SWE.4-GP5 | 过程角色分配 | 各角色职责已定义 | ✅ | 小马 🐴 |
| SWE.4-GP6 | 基础设施 | pytest + coverage + RTM | 🟡 RTM 待集成 | 后端组 |
| SWE.4-GP7 | 过程理解 | 培训手册 + 贡献者指南 | ✅ | 小马 🐴 |

### 6.2 SWE.5 AL2 检查表

| # | GP 要求 | 证据 | 状态 | 负责人 |
|:--|:--------|:-----|:----:|:------|
| SWE.5-GP1 | 集成测试策略已定义 | ❌ 缺少 `docs/swe5-integration-strategy.md` | 🔴 | 老陈 |
| SWE.5-GP2 | 集成测试规划 | CI pipeline 层次定义 | ✅ | CI 组 |
| SWE.5-GP3 | 回归测试策略 | ❌ 无文档化策略 | 🔴 | 后端组 |
| SWE.5-GP4 | 接口测试 | ❌ 无跨模块契约测试 | 🔴 | 后端组 |
| SWE.5-GP5 | 测试环境管理 | dev/CI/HIL 环境文档 | 🟡 不完整 | 硬件组 |
| SWE.5-GP6 | 结果记录与追溯 | CI artifacts + JUnit | ✅ | CI 组 |

### 6.3 SUP.9 AL2 检查表（变更管理）

| # | GP 要求 | 证据 | 状态 | 负责人 |
|:--|:--------|:-----|:----:|:------|
| SUP.9-GP1 | 变更请求流程 | Git PR + issue tracker | ✅ | 全组 |
| SUP.9-GP2 | 变更影响分析 | `docs/spec-delta-*.md` | ✅ | 架构组 |
| SUP.9-GP3 | 变更追溯 | spec-delta + RTM | 🟡 RTM 待集成 | 后端组 |
| SUP.9-GP4 | 变更审批 | PR review 流程 | ✅ | 架构评审 |

---

## 7. 审计准备清单

### 7.1 审计前检查

- [ ] 所有 ASPICE 过程域评估 ≥AL1（无 AL0）
- [ ] SWE.4 过程域 ≥70% AL2
- [ ] SWE.5 过程域 ≥50% AL2
- [ ] ISO 26262-8 工具分类矩阵完成 ✅
- [ ] TCL2 认证：yuleosh CLI, OpenSpec, CI Pipeline ✅
- [ ] TCL3 认证：coverage 工具 ✅
- [ ] 工具认证证据文档完 ✅
- [ ] RTM 追溯矩阵 100% 覆盖 SHALL ✅
- [ ] 所有测试用例通过 ✅

### 7.2 审计产出物清单

审计准备期间，以下产出物 SHALL 全部就位：

```
docs/
├── rtm-spec.md                          ← RTM 规范（已就绪）
├── rtm-ci-integration.md                ← RTM CI 集成（已就绪）
├── ci-coverage-gateway.md               ← 覆盖率阶梯（已就绪）
├── test-coverage-standards.md           ← 测试覆盖标准（已就绪）
├── contributor-testing-guide.md         ← 贡献者指南（已就绪）
├── aspice-readiness-assessment.md       ← 本文件（已就绪）
├── swe4-test-spec.md                    ← SWE.4 测试规范（M1 产出）
├── swe5-integration-strategy.md         ← SWE.5 集成策略（M2 产出）
├── swe6-confirmation-spec.md            ← SWE.6 确认测试（M2 产出）
├── tool-qualification.md               ← 工具置信度文档（M3 产出）
├── sil-qualification.md                ← SIL 认证文档（M3 产出）
├── hil-qualification.md                ← HIL 认证文档（M2 产出）
├── rtm-exceptions.md                    ← 门禁例外记录
└── coverage-debt.md                     ← 覆盖率债务记录

artifacts/
├── rtm/                                 ← RTM 快照目录
├── coverage/                            ← 覆盖率报告
├── evidence/                            ← 合规证据包
└── audit/                               ← 审计打包产物
```

### 7.3 审计证据包结构

```bash
audit-evidence-v{version}.zip
├── 01-SYS1-system-requirements/
│   ├── spec.md
│   ├── spec-validate-report.json
│   └── spec-review-evidence.md
├── 02-SWE1-software-requirements/
│   ├── swe1-requirements.json
│   └── rtm-v{version}.json
├── 03-SWE4-unit-verification/
│   ├── test-summary.html
│   ├── coverage-report/
│   ├── junit-results.xml
│   └── rtm-report.json
├── 04-SWE5-integration-test/
│   ├── sil-test-report.json
│   ├── hil-report.json
│   └── integration-strategy.md
├── 05-SWE6-confirmation/
│   ├── release-notes.md
│   └── confirmation-test-report.md
├── 06-SUP9-change-management/
│   ├── spec-delta-*.md
│   └── pr-audit-log.json
├── 07-ISO-26262-8-tool-qualification/
│   ├── tool-qualification.md
│   ├── tool-classification-matrix.json
│   └── tool-validation-results/
└── audit-checklist.md
```

---

## 8. 风险与缓解

### 8.1 主要风险

| 风险 | 可能性 | 影响 | 缓解策略 |
|:-----|:------:|:----:|:---------|
| RTM 集成开发资源不足 | 🟡 中 | 高 | 优先投入后端组 1 人/月 |
| cross/*.py 模块（硬件交互）测试难以自动化 | 🔴 高 | 高 | HIL mock 模式 + 硬件抽象层 |
| 分支覆盖工具链不成熟 | 🟡 中 | 中 | 选择覆盖工具（pytest-cov 集成） |
| TCL3 认证标准不清晰 | 🟡 中 | 中 | 参考 ISO 26262-8 §8.4.3 标准解释 |
| 团队 ASPICE 经验不足 | 🟡 中 | 中 | 聘请 ASPICE 顾问做一次预评估 |
| 时间窗口与功能开发冲突 | 🟡 中 | 高 | 在 Sprint Planning 中预留 20% 质量 Sprint |

### 8.2 依赖项

| 依赖 | 类型 | 交付时间 | 关键路径？ |
|:-----|:-----|:---------|:---------:|
| yuleosh rtm 命令实现 | 内部开发 | 2026-Q3 W4 | ✅ 是 |
| 分支覆盖跟踪 | 内部开发 | 2026-Q3 W4 | ✅ 是 |
| 接口契约测试框架 | 内部开发 | 2026-Q4 W4 | ✅ 是 |
| QEMU SIL 认证 | 硬件组 | 2027-Q1 W8 | ⛔ 否 |
| ASPICE 顾问预评估 | 外部 | 2027-Q1 W8 | ⛔ 否 |

---

## 附录 A: ASPICE 4.0 过程域映射

| 编号 | 过程域 | AL1 目标 | AL2 目标 | yuleOSH 文档映射 |
|:----|:-------|:-------:|:-------:|:-----------------|
| SYS.1 | 系统需求分析 | 100% | 80% | `docs/spec.md` |
| SYS.2 | 系统架构设计 | 80% | 50% | `docs/architecture.md` |
| SYS.3 | 系统设计 | 80% | 40% | — |
| SYS.4 | 系统集成与测试 | 70% | 40% | `docs/hil-testing.md` |
| SYS.5 | 系统确认与发布 | 70% | 40% | Release notes |
| SWE.1 | 软件需求分析 | 100% | 80% | `docs/spec.md`, OpenSpec |
| SWE.2 | 软件架构设计 | 90% | 60% | `docs/architecture.md` |
| SWE.3 | 软件详细设计 | 80% | 50% | `docs/design/` |
| SWE.4 | 软件单元验证 | **100%** | **≥70%** | 本文档路线图目标 |
| SWE.5 | 软件集成与测试 | 90% | **≥50%** | 本文档路线图目标 |
| SWE.6 | 软件确认与发布 | 80% | **≥50%** | 本文档路线图目标 |
| SUP.9 | 变更管理 | 90% | 70% | spec-delta + PR |
| SUP.10 | 配置管理 | 90% | 60% | git + CI artifacts |

## 附录 B: 版本历史

| 版本 | 日期 | 变更说明 |
|:----|:----|:--------|
| v1.0.0 | 2026-06-14 | 初始版本：ASPICE 差距分析、路线图 M0→M3、工具分类矩阵 |

---

*本文档定义了 yuleOSH 从当前状态到 ASPICE AL2 / ISO 26262-8 TCL2 认证的完整路线图。各里程碑及其交付项为 SHALL 级要求，差距项为项目质量决策提供依据。*
