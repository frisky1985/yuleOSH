# yuleOSH 集成策略文档

> **文档编号**: INT-yuleOSH-001
> **合规标准**: ASPICE SWE.5.BP1 — 制定包括回归测试策略在内的集成策略
> **适用版本**: yuleOSH 2.2.0
> **状态**: ✅ Released — CL1 合规
> **最后更新**: 2026-07-15

---

## 修订历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| 1.0.0 | 2026-07-15 | 初始发布 — 定义 CI 多层集成策略、测试层级映射、SWE.5 合规证据 | 小马 |

---

## 1. 引入

### 1.1 目的

本文档定义 yuleOSH 项目的**集成测试策略**，确保每个软件增量（代码变更）都经过系统化的递增式集成验证，从单元级验证逐步演进到系统级确认，最终满足 ASPICE SWE.5（软件集成测试）的合规要求。

核心目标：

1. **定义测试层级结构** — 单元测试 → 集成测试 → SIL → HIL 的递进关系
2. **明确门禁条件** — 每层通过的判定标准及阻断条件
3. **建立追溯链条** — 测试结果 ↔ 需求 ↔ 变更的可追溯性
4. **确认回归策略** — 变更触发哪些层级的回归测试
5. **度量覆盖充分性** — 各层级的覆盖目标和当前基线

### 1.2 适用范围

本文档适用于以下测试范围：

- Python 单元测试（pytest）
- C/C++ 单元测试（Ceedling / Unity / CMock）
- 集成测试（跨模块交互验证）
- SIL 测试（QEMU 仿真 + HAL Mock）
- HIL 测试（目标硬件运行）
- E2E 测试（端到端流程验证）
- 回归测试套件（各层级全量/增量）

### 1.3 定义与缩略语

| 术语 | 含义 |
|------|------|
| SWE.5 | ASPICE Software Integration Test — 软件集成测试 |
| L1/L2/L3 | CI 三层：开发验证 / 集成验证 / 系统验证 |
| SIL | Software-in-the-Loop — 软件在环仿真 |
| HIL | Hardware-in-the-Loop — 硬件在环测试 |
| UT | Unit Test — 单元测试 |
| IT | Integration Test — 集成测试 |
| E2E | End-to-End — 端到端测试 |
| MISRA | Motor Industry Software Reliability Association — 汽车工业软件可靠性协会 |
| SUT | System Under Test — 被测系统 |

### 1.4 参考文档

| 编号 | 文档 | 版本 |
|------|------|------|
| [R01] | yuleOSH 软件需求规格说明书 | 1.0.0 |
| [R02] | yuleOSH 系统架构文档 | 1.0.0 |
| [R03] | yuleOSH 规范文档 (OpenSpec) | 2.2.0 |
| [R04] | HIL 集成策略 | 1.0.0 |
| [R05] | MISRA 验证计划 | 1.0.0 |
| [R06] | 证据包结构文档 | 1.0.0 |

---

## 2. 集成策略总览

### 2.1 核心原则

1. **递进式集成** — 单元测试通过后进入集成测试，集成测试通过后进入 SIL/HIL
2. **门禁阻断** — 上层执行的前提条件是下层全部通过
3. **分层隔离** — 每一层独立运行，错误不扩散到其他层
4. **回归驱动** — 代码变更触发从最底层到变更影响层的全量回归
5. **证据自生** — 每层测试结果自动纳入 ASPICE 证据包

### 2.2 分层架构

```
                      ┌──────────────────────┐
                      │      L3: 系统验证      │
                      │  SWE.6 确认测试        │
                      │  E2E 端到端测试        │
                      │  证据包生成            │
                      │  Release 门禁          │
                      └──────────┬───────────┘
                                 │ 依赖 L2 通过
                      ┌──────────▼───────────┐
                      │   L2.5: HIL 测试      │
                      │   目标硬件运行          │
                      │   烧录、串口、GDB      │
                      │   可选（mock/fake 模式）│
                      └──────────┬───────────┘
                                 │ 依赖 L2 通过
                      ┌──────────▼───────────┐
                      │      L2: 集成验证      │
                      │  SWE.5 集成测试        │
                      │  SIL 软件在环          │
                      │  交叉编译验证          │
                      │  静态分析（MISRA）     │
                      │  MR 门禁              │
                      └──────────┬───────────┘
                                 │ 依赖 L1 通过
                      ┌──────────▼───────────┐
                      │      L1: 开发验证      │
                      │  SWE.4 单元验证        │
                      │  Python UT + C UT     │
                      │  覆盖率门禁            │
                      │  规范/架构审查         │
                      │  文档同步检查          │
                      │  Commit 门禁          │
                      └──────────────────────┘
```

### 2.3 分层触发策略

| 层 | 代码 | 触发事件 | 执行环境 | 最大时长 |
|----|------|---------|---------|---------|
| L1 | CI 层 1 | Commit/Push | CI Runner (GitHub Actions) | 30s |
| L2 | CI 层 2 | PR/MR 创建或更新 | CI Runner (GitHub Actions) | 120s |
| L2.5 | CI 层 2.5 | PR/MR Merge（可选） | CI Runner + 硬件目标 | 180s |
| L3 | CI 层 3 | Release/Tag 创建 | CI Runner (GitHub Actions) | 300s |

### 2.4 集成策略演进路径

```
开发阶段                      集成阶段                  确认阶段
┌─────────────┐    ┌─────────────────────┐    ┌────────────────┐
│ 单元测试     │ →  │ 集成测试             │ →  │ 确认测试        │
│ (UT)        │    │ (IT)                │    │ (Confirmation) │
│ per function │    │ inter-module        │    │ end-to-end     │
│ SWE.4       │    │ SWE.5               │    │ SWE.6          │
└─────────────┘    └──────────┬──────────┘    └────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
      ┌────────────┐ ┌────────────┐ ┌────────────┐
      │ SIL Test   │ │ HIL Test   │ │ Regression │
      │ QEMU仿真   │ │ 目标硬件    │ │ 全量回归    │
      │ SWE.5      │ │ SWE.5/6    │ │ SWE.5      │
      └────────────┘ └────────────┘ └────────────┘
```

---

## 3. CI 多层集成策略

### 3.1 L1 — 开发验证（Commit Gate）

**ASPICE 对应**: SWE.4（软件单元验证）

**目标**: 每次代码提交后快速验证基本正确性

**触发**: 任意分支的 Commit/Push

**阶段**:

| 阶段 | 内容 | 工具/框架 | 阻断性 |
|------|------|----------|--------|
| YAML 验证 | 检查 YAML 配置文件格式 | `yaml_validator.py` | 阻断 |
| 规范验证 | 验证 Spec 格式正确性 | `spec.validate` | 阻断 |
| 架构审查 | 自动审查架构一致性 | `run_architecture_review()` | 阻断 |
| 需求追溯校验 | 验证 REQ-xxx 在代码中的可追溯性 | `run_requirements_trace()` | 阻断 |
| Plan Lint | 检验开发计划 YAML | `run_plan_lint()` | 阻断 |
| Doc Sync Gate | 文档与代码同步检查 | `run_docsync_gate()` | 阻断 |
| Clang-Tidy | C/C++ 代码静态分析 | `run_clang_tidy()` | 阻断 |
| MISRA 检查 | MISRA C:2023 规则验证（delta 模式） | `run_misra_check(delta=True)` | 阻断 |
| 单元测试 | Python pytest + C 单元测试 | `run_unit_tests()` | 阻断 |
| 覆盖率检查 | 行覆盖率 ≥ 80%，分支覆盖率 ≥ 60% | `run_coverage_check()` | 阻断 |
| C 覆盖率 | C 代码 gcov 覆盖率收集 | `run_c_coverage()` | 非阻断 |
| C 覆盖率门禁 | C 代码行覆盖率 ≥ 70% | `run_c_coverage_check()` | 阻断 |

**通过条件**: 所有阻断阶段通过 | **超时**: 30s（可配置 `CI_LAYER1_TIMEOUT`）

**L1 依赖**: 无（最低层，无前置依赖）

### 3.2 L2 — 集成验证（MR Gate）

**ASPICE 对应**: SWE.5（软件集成测试）

**目标**: 验证跨模块交互正确性、交叉编译产物行为、SIL 仿真

**触发**: PR/MR 创建或更新（隐含 L1 通过）

**依赖检查**: `check_layer_dependency(2, project_dir)` — 检查 L1 结果是否存在且通过，未通过则阻断

**阶段**:

| 阶段 | 内容 | 工具/框架 | 阻断性 |
|------|------|----------|--------|
| 交叉编译 | ARM/RISC-V/x86_64 交叉编译验证 | `_cross_compile_stage()` | 阻断 |
| 静态分析 | C/C++ 全量 MISRA + Clang-Tidy | `_static_analysis_stage()` | 阻断 |
| SIL 测试 | QEMU 系统仿真测试 | `run_sil_tests()` | 阻断 |
| 集成测试 | 跨模块 Python 集成测试 | `_integration_test_stage()` | 阻断 |
| 内存安全 | ASan 配置检查（不实际运行） | 文件存在性检查 | 非阻断 |

**通过条件**: 所有阻断阶段通过 | **超时**: 120s

**L2 依赖**: L1 必须在最近一次 commit 中通过

### 3.3 L2.5 — HIL 测试（可选硬件门禁）

**ASPICE 对应**: SWE.5（软件集成测试 — 硬件目标）/ SWE.6（确认测试 — 产品级环境）

**目标**: 在目标硬件上验证嵌入式软件行为

**触发**: PR/MR Merge 前（可选，取决于环境可用性）

**依赖检查**: `check_layer_dependency(25, project_dir)` — 检查 L2 结果是否存在且通过

**模式选择**:

| 模式 | 说明 | 使用场景 |
|------|------|---------|
| `mock: true` | 模拟 HIL，所有硬件交互 fake | CI 环境无物理板时 |
| `mock: false` | 真实硬件测试 | 专用 HIL 环境 |

**阶段**:

| 阶段 | 内容 | 工具/框架 | 阻断性 |
|------|------|----------|--------|
| 目标检测 | 检测板子是否在线（mock 模式模拟） | `_detect_hil_target()` | 阻断 |
| HIL 测试 | 烧录 + 串口断言 | `_run_hil_mock_tests()` / `_run_hil_real_tests()` | 阻断 |
| HIL 报告 | 测试结果保存 | `_save_hil_report()` | 非阻断 |

**通过条件**: 所有阻断阶段通过（mock 模式下模拟通过即算通过）

**L2.5 依赖**: L2 必须在最近一次 commit 中通过

### 3.4 L3 — 系统验证（Release Gate）

**ASPICE 对应**: SWE.6（软件确认测试）

**目标**: 发布前全量验证，包括端到端测试、版本检查、证据包生成

**触发**: Release/Tag 创建

**阶段**:

| 阶段 | 内容 | 工具/框架 | 阻断性 |
|------|------|----------|--------|
| E2E 测试 | 端到端流程验证 | `pytest tests/e2e` | 阻断 |
| 版本检查 | 确认 pyproject.toml 版本号 | `tomllib.load()` | 非阻断 |
| 证据包生成 | 生成 ASPICE 合规证据包 | `evidence.pack.generate_evidence()` | 非阻断（有 warning 可接受） |

**通过条件**: 所有阻断阶段通过 | **超时**: 300s

**Dashboard 更新**: L3 完成后自动调用 `run_dashboard_update()`，写入 SWE Status + 覆盖率趋势 + KPI 趋势

---

## 4. 测试层级与 ASPICE SWE.5 映射

### 4.1 SWE.5 BP 逐项对照

| BP ID | BP 描述 | yuleOSH 实现 | 测试层级 | 触发条件 |
|-------|---------|-------------|---------|---------|
| **SWE.5.BP1** | 制定包括回归测试策略在内的集成策略 | `docs/integration-strategy.md`（本文档） | — | 策略文档 |
| **SWE.5.BP2** | 开发集成测试规范包括测试用例的验收准则 | `docs/spec.md` — SWR-xxx 中的 GIVEN/WHEN/THEN 验收条件 | L1/L2 | 规格评审 |
| **SWE.5.BP3** | 集成测试项和测试用例的选择/生成 | `pipeline/step_handlers/test_integration.py` + `testgen/` 自动生成 | L2 | MR 创建 |
| **SWE.5.BP4** | 测试已集成的软件项 | `run_layer2()` — SIL + 集成测试 | L2 | MR 更新 |
| **SWE.5.BP5** | 根据需要建立双侧可追溯性 | `knowledge_graph.queries` — `get_confirmation_trace()` 返回 validates 边 | L2/L3 | 每次 CI 运行 |
| **SWE.5.BP6** | 确保集成测试和软件架构的一致性 | `ci/stages/traceability.py` + CI L3 一致性检查 | L3 | Release |
| **SWE.5.BP7** | 汇总集成测试结果并与相关方沟通 | Dashboard SWE Status + CI Report | L3 后 | 每次 CI 运行 |

### 4.2 测试层级 → SWE 映射矩阵

```
测试层级         SWE 映射         验证目标                 追溯边
─────────       ─────────         ──────────               ──────
L1 UT (Python)  SWE.4             函数级正确性             covers (unit)
L1 UT (C)       SWE.4             C 函数行为              covers (unit)
L1 MISRA        SWE.4             代码规范                —（工具验证）
L2 SIL          SWE.5             跨组件集成运行时         validates (sil)
L2 集成测试     SWE.5             模块间接口协议           validates (integration)
L2.5 HIL        SWE.5/SWE.6       目标硬件运行时行为        validates (hil/system)
L3 E2E          SWE.6             端到端业务流程           validates (system)
Dashboard SWE   SWE.4/5/6/8/10    ASPICE 状态判定          KG 语义追溯
```

### 4.3 知识图谱中的测试层级语义

yuleOSH 知识图谱使用`validates` 边表示确认测试关系，使用 `covers` 边表示验证测试关系，两者在 ASPICE 语义上严格分离：

| 边类型 | 测试层级 | ASPICE 含义 | 代码位置 |
|--------|---------|-------------|---------|
| `covers` + `layer: unit` | 单元测试 | SWE.4 单元验证 | `_annotate_covers_layer()` |
| `validates` + `layer: integration` | 集成测试 | SWE.5 集成测试 | `_build_validates_edges()` |
| `validates` + `layer: sil` | SIL 测试 | SWE.5 软件集成 | `_build_validates_edges()` |
| `validates` + `layer: hil` | HIL 测试 | SWE.5 集成 / SWE.6 确认 | `_build_validates_edges()` |
| `validates` + `layer: system` | 系统/E2E 测试 | SWE.6 确认测试 | `_build_validates_edges()` |

---

## 5. 回归测试策略

### 5.1 回归触发条件

每次代码变更触发回归测试的层级取决于变更范围和受影响模块：

| 变更类型 | 触发回归层级 | 说明 |
|----------|-------------|------|
| 纯文档变更（`.md` 文件） | L1（Doc Sync Gate） | 无需代码回归 |
| Python 工具函数修改 | L1（UT）+ L2（集成测试） | 调用链可能涉及集成测试 |
| C 源代码修改 | L1（UT + MISRA）+ L2（SIL） | 嵌入式代码必须过 SIL |
| CI 配置修改 | L1 + L2 + L3 | 影响 CI 流水线自身 |
| 接口/API 签名变化 | L1 + L2 + L3 | 向后兼容性验证 |
| 依赖变化（Python 包） | L1 + L2 | 功能不变性验证 |
| Dashboard/KG 变更 | L1 + L2 + L3 | 影响证据包和合规状态 |

### 5.2 回归范围判定

```
变更发生
  │
  ▼
┌───────────────────────┐
│ 确定变更文件           │
│ git diff --name-only  │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 查询 KG 影响链         │
│ impact_analysis()     │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 确定受影响测试         │
│ 直接 + 间接依赖       │
└──────────┬────────────┘
           ▼
┌───────────────────────┐
│ 运行受影响层级回归     │
│ 从最低层开始逐级递增   │
└───────────────────────┘
```

### 5.3 回归策略选择

| 策略 | 说明 | 使用场景 |
|------|------|---------|
| **全量回归** | 运行所有层级的全部测试 | Release/Tag 构建（L3 触发） |
| **部分回归** | 仅运行受影响模块和上下游依赖的测试 | MR 阶段（KG impact_analysis 辅助） |
| **增量回归** | 仅运行 L1 → 通过后运行 L2 → 通过后运行 L2.5→ L3 | 日常 commit 和 PR |
| **跳过回归** | 不运行任何测试（仅用于文档/CI 配置变更验证后） | 纯文档变更经 Doc Sync Gate 验证后 |

---

## 6. 当前覆盖情况

### 6.1 测试数量分布

| 测试层级 | 测试文件数 | 测试函数数 | 通过率 | 覆盖模块 |
|----------|-----------|-----------|--------|---------|
| L1 — Python UT | 140+ | 1944+ | 100% | 全部 Python 模块 |
| L1 — C UT | 10+ | 50+ | 100% | NVM, Memory, Fault, Platform |
| L1 — MISRA 验证 | 1 (benchmark) | — | — | MISRA 规则集验证 |
| L2 — SIL 测试 | 5+ | 20+ | 100% | QEMU SIL Runner 集成 |
| L2 — 集成测试 | 15+ | 80+ | 100% | 跨模块集成 |
| L2.5 — HIL 测试 | 5+ | 20+ | 100% (mock) | 硬件抽象 |
| L3 — E2E 测试 | 3+ | 15+ | 100% | 端到端流程 |
| **合计** | **180+** | **2130+** | **100%** | — |

### 6.2 覆盖率基线

| 度量 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| Python 行覆盖率 | 76% | ≥80% | 🟡 接近目标 |
| Python 分支覆盖率 | 62% | ≥60% | 🟢 达标 |
| C 行覆盖率 | 82% | ≥70% | 🟢 达标 |
| 需求→测试追溯覆盖率 | 89% | ≥95% | 🟡 接近目标 |
| KG 节点覆盖率（需追溯） | 96% | ≥98% | 🟡 接近目标 |

### 6.3 SWE.5 BP 覆盖状态

| BP | 状态 | 当前实现 | 缺口 |
|----|------|---------|------|
| BP1 — 集成策略 | ✅ 已覆盖 | `docs/integration-strategy.md`（本文档） | — |
| BP2 — 集成测试规范 | ✅ 已覆盖 | `docs/spec.md` SWR-xxx + 测试用例验收准则 | — |
| BP3 — 测试用例选择 | 🟡 部分覆盖 | `test_integration.py` 自动生成 + `testgen/` 模板 | 自动生成尚不覆盖所有场景 |
| BP4 — 已集成软件项测试 | ✅ 已覆盖 | L2 run_layer2() SIL + 集成测试 | — |
| BP5 — 双侧可追溯性 | ✅ 已覆盖 | KG validates 边（4 层）+ `get_confirmation_trace()` | — |
| BP6 — 架构一致性 | ✅ 已覆盖 | CI L3 traceability + Doc Sync Gate | — |
| BP7 — 结果汇总与沟通 | ✅ 已覆盖 | Dashboard SWE Status + CI Report + Feishu 通知 | — |

### 6.4 已知测试覆盖缺口

| 缺口 | 层级 | 影响 | 计划修复 |
|------|------|------|---------|
| 知识图谱增量构建引擎未覆盖 | L2 | 全量 bootstrap 性能瓶颈（~11K 节点） | P2 计划 |
| PostgreSQL 后端未在 CI 中验证 | L2 | `queries_pg.py` RECURSIVE CTE 无测试覆盖 | P2 计划 |
| C 覆盖率门禁 >70% 尚有 5 个模块需补充测试 | L1 | 部分 C 模块覆盖率不足 | Sprint 1.1 |
| E2E 测试用例数量偏少（15+） | L3 | 无法覆盖所有业务流程路径 | P2 计划 |

---

## 7. Dashboard 在集成策略中的角色

### 7.1 Dashboard 数据来源

```
┌──────────────────┐
│  CI L1/L2/L3     │
│  运行结果         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  .osh/ci/         │
│  layer*.json     │
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────────┐
│ File   │ │ KG Store   │
│ Probe  │ │ (semantic) │
└────────┘ └──────┬─────┘
                  │
                  ▼
         ┌──────────────────┐
         │ dashboard_writer  │
         │ write_swe_status()│
         │ write_coverage()  │
         │ write_kpi()       │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ swe-status.jsonl  │
         │ coverage-trend.* │
         │ process-kpi.jsonl │
         └────────┬─────────┘
                  │
                  ▼
         ┌──────────────────┐
         │ Dashboard UI     │
         │ (http.server)    │
         └──────────────────┘
```

### 7.2 Dashboard 更新的集成时间点

| 事件 | 更新内容 | 数据源 |
|------|---------|--------|
| CI L1 完成 | 覆盖率趋势 | `write_coverage_trend()` |
| CI L2 完成 | SIL/集成测试结果 | `.osh/ci/layer2-*.json` |
| CI L2.5 完成 | HIL 测试结果 | HIL 报告 |
| CI L3 完成 | SWE Status + KPI + 全部趋势 | KG (优先) + 文件探针 (降级) |
| Release 完成 | 最终 SWE Status | `run_dashboard_update()` 全量更新 |

### 7.3 KG 数据的三级降级策略

```
KG 数据请求
  │
  ├── KG Store 不存在 ──────→ {} (空字典 → 文件探针)
  │
  ├── KG 模块不可导入 ──────→ _check_kg_available()=False → {}
  │
  └── KG 查询异常 ─────────→ try/except → {}
         │
         ▼
   返回空字典
   调用方降级到文件探针
```

---

## 8. ASPICE SWE.5 合规自检

### 8.1 BP 逐项对照

| BP ID | BP 描述 | 合规状态 | 对应文档/模块 | 证据 |
|-------|---------|----------|-------------|------|
| **SWE.5.BP1** | 制定包括回归测试策略在内的集成策略 | ✅ **Fully** | `docs/integration-strategy.md`（本文档） | 本文档 §2-§5 定义集成策略 |
| **SWE.5.BP2** | 开发集成测试规范包括测试用例的验收准则 | ✅ **Fully** | `docs/spec.md` + `docs/software-requirements.md` | 每项 SWR-xxx 含 GIVEN/WHEN/THEN |
| **SWE.5.BP3** | 集成测试项和测试用例的选择/生成 | 🟡 **Largely** | `pipeline/step_handlers/test_integration.py` | 自动生成 + 模板，部分场景仍需手工 |
| **SWE.5.BP4** | 测试已集成的软件项 | ✅ **Fully** | `ci/layers.py` → `run_layer2()` | 交叉编译 + SIL + 集成测试 |
| **SWE.5.BP5** | 根据需要建立双侧可追溯性 | ✅ **Fully** | `knowledge_graph.queries.get_confirmation_trace()` | validates 边（integration/sil/hil/system） |
| **SWE.5.BP6** | 确保集成测试和软件架构的一致性 | ✅ **Fully** | `ci/stages/traceability.py` + `ci/sync_check.py` | CI L3 一致性检查 |
| **SWE.5.BP7** | 汇总集成测试结果并与相关方沟通 | ✅ **Fully** | Dashboard SWE Status + CI Report + Feishu 通知 | 自动推送 |

### 8.2 证据清单

| 证据项 | 路径/来源 | 对应的 BP |
|--------|----------|-----------|
| 集成策略文档 | `docs/integration-strategy.md` | BP1 |
| 集成测试规范 | `docs/spec.md` — SWR-xxx | BP2 |
| 集成测试用例 | `pipeline/step_handlers/test_integration.py` | BP3 |
| SIL 测试结果 | `.osh/reports/sil-results/` | BP4 |
| 交叉编译日志 | CI 输出日志 | BP4 |
| 双侧追溯报告 | KG `get_confirmation_trace()` 输出 | BP5 |
| 一致性检查报告 | `ci/stages/traceability.py` 输出 | BP6 |
| 集成测试报告 | CI Report + Dashboard SWE Status | BP7 |

### 8.3 持续合规流程

```bash
# 1. 更新本文档后验证合规性
yuleosh ci run 1  # L1: 规范验证 + 架构审查

# 2. 更新集成测试后运行 L2
yuleosh ci run 2  # L2: SIL + 集成测试

# 3. 有硬件环境时运行 L2.5
yuleosh ci run 25 # L2.5: HIL

# 4. 发布前运行全量
yuleosh ci run 3  # L3: E2E + 证据包

# 5. 更新 Dashboard
yuleosh ci dashboard-update  # 写入 SWE Status
```

---

## 9. 附录 A — 测试层级配置示例

### 9.1 `ci-config.yaml` 集成策略配置

```yaml
# yuleOSH CI 集成策略配置
integration:
  # L1 配置
  layer1:
    timeout: 30
    fail_fast: true
    stages:
      - yaml-validation
      - spec-validation
      - architecture-review
      - requirements-trace
      - plan-lint
      - docsync-gate
      - clang-tidy
      - misra-check
      - unit-tests
      - coverage
      - c-coverage

  # L2 配置
  layer2:
    timeout: 120
    dependencies: [1]  # L1 必须通过
    stages:
      - cross-compile
      - static-analysis
      - sil-tests
      - integration-tests

  # L2.5 HIL 配置
  layer_25:
    enabled: true
    timeout: 180
    dependencies: [2]
    hardware-test:
      mock: true
      firmware: build/firmware.elf
      test_scripts_dir: tests/hil
      boot_pattern: "Boot Complete"

  # L3 配置
  layer3:
    timeout: 300
    stages:
      - e2e-tests
      - version-check
      - evidence-pack

  # 回归策略
  regression:
    default: full  # full | partial | incremental
    partial:
      enabled: true
      impact_api: true  # 使用 KG impact_analysis() API
    skip_for_docs_only: true
```

### 9.2 环境变量影响

| 环境变量 | 影响 | 默认值 |
|----------|------|--------|
| `CI_LAYER1_TIMEOUT` | L1 超时时长 | 30s |
| `YULEOSH_HIL_MOCK` | HIL mock 模式 | true |
| `YULEOSH_DB_URL` | KG 数据库 URL | SQLite (默认) |

---

## 附录 B — 修订历史

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| 1.0.0 | 2026-07-15 | 初始发布 — 定义 CI 多层集成策略、测试层级映射、SWE.5 合规证据 | 小马 |

## 附录 C — 关键术语

| 术语 | 含义 |
|------|------|
| ASPICE | Automotive SPICE — 汽车行业软件过程改进和能力测定 |
| SWE.5 | Software Integration Test — 软件集成测试过程域 |
| BP | Base Practice — ASPICE 基础实践 |
| SIL | 软件在环 (Software-in-the-Loop) — 使用 QEMU 仿真 |
| HIL | 硬件在环 (Hardware-in-the-Loop) — 在目标硬件上测试 |
| E2E | 端到端 (End-to-End) — 全流程验证 |
| MISRA | Motor Industry Software Reliability Association — 汽车工业软件可靠性协会 |
| KG | 知识图谱 (Knowledge Graph) — 追溯关系图数据库 |
| validates | 确认边 — 表示测试验证了代码/需求（integration/sil/hil/system 层） |
| covers | 覆盖边 — 表示测试覆盖了代码/需求（unit 层） |

---

*文档结束 — yuleOSH 集成策略合规证据，ASPICE SWE.5.BP1 满足。*
