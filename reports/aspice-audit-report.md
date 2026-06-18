# 🧾 yuleOSH ASPICE V-Model 合规审计报告

> **审计人**: 老陈 👨‍🏫（前博世资深架构师 / ASPICE 内部/外部审计师）
> **审计日期**: 2026-06-18
> **审查对象**: yuleOSH Pipeline（23 步 PIPELINE_STEPS + CI 4 层）
> **参考依据**: `__init__.py` / `layers.py` / `expert-pipeline-assessment4.md`（85 分）

---

## 1️⃣ 审计清单逐项评分

### SWE.1 — 需求获取（Requirements Elicitation）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有需求定义步骤 | ✅ | `spec-check`（OpenSpec 合规）+ `super-analysis`（S.U.P.E.R 启动分析）+ `prd`（产品需求文档）— 三步需求定义，从合规检查到产品级需求分析，覆盖完整需求获取链路 |
| 有需求审查机制 | ✅ | `prd-review`（PRD 质量审查）— PRD 产出后立即进入质量审查，有小马（Hermes）做 peer review |
| 需求可追溯到后续验证 | ✅ | `traceability.py` LRM/LRT 引擎：`extract_shall_statements()` → `generate_lrm()` → `generate_lrt()`，支持从需求到代码、测试的双向追溯。78 分水平，实际覆盖度取决于现有代码注释标记（`# REQ: SHALL-N`），但引擎架构完整 |

**SWE.1 结论**: ✅ **通过**。需求侧三步流程 + 审查门禁 + 追溯引擎构成完整链路。弱点是代码匹配依赖注释标记，无标记源码回退精度有限。

---

### SWE.2 — 系统架构设计（System Architectural Design）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有架构设计步骤 | ✅ | `architecture`（Claude 架构设计）— 专用架构设计 Agent，使用 Claude 模型处理 |
| 有架构审查 | ✅ | `arch-review`（架构审查）— 小克做 architecture review，有专门 handler `step_review_arch` |
| 架构到需求的追溯 | ✅ | `traceability.py` `generate_lrm()` 生成需求↔代码双向矩阵，架构产出物可通过 LRM 追溯到需求。Architecture 产出物本身就是 SWE.1→SWE.2 的追溯产物 |

**SWE.2 结论**: ✅ **通过**。架构设计与审查分离，且架构审查步骤独立于开发代码审查。追溯引擎提供 LRM 矩阵。

---

### SWE.3 — 详细设计（Detailed Design）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有详细设计/开发步骤 | ✅ | `development`（开发计划与代码实现）+ `test-planning`（测试规划）— Claude 完成代码实现后，紧接着测试规划，形成设计→计划→开发→审查的闭环 |
| 有计划审查 | ✅ | `devplan-review`（开发计划审查）+ `internal-code-review`（代码实现预审）— 开发计划与代码分别有独立审查环节 |

**SWE.3 结论**: ✅ **通过**。development 步骤涵盖详细设计与实现，devplan-review 和 internal-code-review 形成双重审查门禁。

---

### SWE.4 — 单元验证（Unit Verification）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有单元测试执行 | ✅ | `self-test`（Claude 自测验证）+ `self-test-review`（自测结果审查）— Claude 执行自测 + 小克审查结果 |
| 有 C 级单元测试（嵌入式） | ✅ | `c-unit-test`（C 单元测试 Unity）— 三层降级策略：Unity Makefile runner → Ceedling (`project.yml`) → GCC fallback。含 `_parse_unity_counts()`/`_parse_ceedling_counts()` 双格式解析。无 C 源码时优雅跳过。Pipeline 第 13 步 |
| 有覆盖率检查 | ✅ 部分 | `coverage-review`（测试覆盖审查）— 步骤存在，审查人小马，但 **gcov/lcov 集成未实现**（expert-assessment4 指出 -1 分）。当前覆盖率审查是代码审查层面的定性判断，缺少量化覆盖率数据。CI Layer 1 有 `coverage` 阶段但未说明具体工具链 |

**SWE.4 结论**: ✅ **基本通过**。C 单元测试框架是四轮审查最大突破（0→72 分）。gcov/lcov 覆盖率量化数据缺失是主要短板。

---

### SWE.5 — 集成验证（Integration Verification）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有接口/集成测试 | ✅ | `integration-test`（接口集成测试）+ CI Layer 2（Integration Verification）— 交叉编译 + 集成测试阶段 + SIL 测试 |
| 有静态分析 (MISRA) | ✅ | `misra-review`（MISRA 合规审查）+ CI Layer 1 `misra-check` + `clang-tidy` + CI Layer 2 `static analysis` — 多层 MISRA 合规检查 |
| 有嵌入式特定检查 | ✅ | 四个专用审查步骤：`review-linker`（链接脚本）+ `review-startup`（启动代码）+ `review-rtos`（RTOS 配置）+ `review-memory`（内存安全）。此外 CI Layer 2.5 提供 HIL 测试 |

**SWE.5 结论**: ✅ **强项**。嵌入式检查深度远超一般软件项目。链接脚本、启动代码、RTOS、内存安全四项特定审查 + MISRA + HIL 测试构成完整集成验证体系。

---

### SWE.6 — 合格性验证（Qualification Testing）

| 检查项 | 判定 | 证据 |
|:-------|:----:|:-----|
| 有系统级验收测试 | ✅ | `test-qualification`（合格性测试）+ CI Layer 3（System Verification E2E 测试）+ CI Layer 2.5（HIL） |
| 基于需求的场景测试 | ✅ 部分 | 合格性测试步骤存在，HIL 测试含 mock/real 双模式。但合格性测试用例与需求追溯的关联性依赖 traceability.py 的输出质量，**合格性测试步骤本身是否有基于需求的场景定义需进一步验证** |

**SWE.6 结论**: ✅ **基本通过**。合格性测试 + E2E + HIL 覆盖了场景测试。追溯引擎提供了需求→测试的双向矩阵，但场景测试的完整性取决于实际用例覆盖度。

---

## 2️⃣ CL1 能过吗？

### 判定：**YES ✅** — 可以过 CL1

**理由**：
1. **所有 SWE 过程都有定义**：23 步 PIPELINE_STEPS 完整覆盖 SWE.1→SWE.6。左半侧（需求→设计→开发）9 步，右半侧（单元→集成→合格性）14 步，V-Model 对称性 76 分。

2. **每步都有审查门禁**：
   - PRD review（小马）→ 架构 review（小克）→ 开发计划 review（小克）→ 代码预审（小克）
   - 自测审查（小克）→ MISRA review（小马）→ 覆盖率审查（小马）
   - 嵌入式特定：链接脚本/启动代码/RTOS/内存安全 四项审查

3. **CI 四层自动验证**：
   - L1：plan-lint + clang-tidy + MISRA + 单元测试 + 覆盖率
   - L2：交叉编译 + 静态分析 + SIL + 集成测试 + 内存安全
   - L2.5：HIL（mock/real 双模式）
   - L3：E2E 测试 + 版本检查 + Evidence Pack 生成

4. **追溯能力达标**：LRM/LRT 引擎（78 分）可生成需求↔代码双向追溯矩阵，支持缺口分析和孤儿测试发现。

5. **证据输出机制存在**：Layer 3 自动生成 evidence pack，traceability 产出 `traceability-matrix.json` / `.md`。

**CL1 风险提醒**（非致命，但审计师会问）：
- gcov/lcov 覆盖率量化数据缺失 → 审计时需以覆盖审查记录替代
- 文档-代码同步滞后（7/10 G# 不同步）→ 审计现场需准备人工说明
- `test_c_unit.py` `$$` 临时文件 bug → 修复即可

---

## 3️⃣ CL2 能过吗？

### 判定：**NO ❌** — 当前状态不能过 CL2

**理由**：

| PA 指标 | 判定 | 说明 |
|:--------|:----:|:-----|
| PA 2.1 — 绩效管理 (Performance Management) | ❌ | 无度量数据积累，无过程性能目标定义，无资源规划与监控 |
| PA 2.2 — 工作产品管理 (Work Product Management) | ❌ | 文档同步缺乏门禁，工作产品版本管理规则未定义 |

**CL2 核心缺口**：

1. **零度量体系**：CL2 readiness 评分 40/100（三轮→四轮无变化）。需要：
   - 测试覆盖率趋势数据（gcov/lcov 未集成）
   - 缺陷率/缺陷注入率统计
   - 阶段通过率（比如 CI 各层通过比例）
   - 需求变更率/追溯完整性百分比
   
2. **无过程性能基线**：无历史数据支撑过程能力分析，无法证明过程已被"管理"。

3. **工作产品管理不完整**：
   - 文档-代码同步无自动化门禁
   - 无版本管理策略定义
   - 受审查产品清单未定义（哪些是工作产品？评审准则如何？）

4. **无配置管理证据**：Pipeline 产出物的版本控制、变更历史、发布基线未明确定义。

**CL2 路径**（如果团队想追 CL2）：
1. 集成 gcov/lcov → 获取覆盖率趋势基线
2. 定义 3-5 个关键绩效指标（KPI）
3. 建立度量和冲刺回顾自动报告
4. 实现文档同步 CI 门禁
5. 积累至少 2-3 个 Sprint 的数据

---

## 4️⃣ 如果审计师现场问"你缺什么？"

### 🔴 最关键的三条 Gap

---

### Gap #1: **度量体系真空 — CL2 的绝对障碍**

**严重度**: 🔴 致命（CL2）| 🔶 中度（CL1）

**现状**：
- CL2 readiness 40/100，三轮至四轮零进步
- gcov/lcov 集成未实现（始终 -1 分）
- 覆盖率审查是定性判断，无量化数据
- 无过程性能指标、无趋势分析、无基线数据

**审计师会问**：
> "你们怎么证明单元测试在做？覆盖率是多少？过去两个 Sprint 是改善了还是恶化了？"

**回答不了的问题**：
- 测试覆盖率曲线是多少？
- CI 各层通过率趋势？
- 平均缺陷发现阶段位置？

**影响范围**：CL2 全部 PA 指标、SWE.4 量化证据、SWE.6 验收依据

**建议**：
- P0：集成 gcov/lcov → `coverage-review` 步骤获取量化数据
- P1：定义 3 个 KPI（覆盖率、CI 通过率、缺陷逃逸率）
- P2：CI 自动生成趋势报告，每个 Sprint 结束快照

---

### Gap #2: **文档-代码同步缺乏自动化门禁**

**严重度**: 🔶 高度 | 影响全生命周期证据链

**现状**：
- 7/10 G# 优化计划文档状态滞后于代码
- 审计证据完整性受损：审计师更相信文档而非代码
- 四轮审查持续-1.5 分扣分
- 无 CI 门禁检查文档与代码的同步状态

**审计师会问**：
> "这个 PRD 和实际实现一致吗？上次更新是什么时候？"

**审计风险**：证据链断裂。即使代码正确，文档滞后会导致审计师判定过程未受控。ASPICE 是 process-based assessment，文档是过程证据的核心载体。

**建议**：
- P0：增加 CI 步骤检查文档最后修改时间 vs. 代码最后修改时间
- P1：建立"文档更新"作为 Pipeline 步骤的必要前置条件
- P2：定义文档状态标签（current/stale/outdated）

---

### Gap #3: **gcov/lcov 覆盖率集成缺失 — 单元验证的证据空洞**

**严重度**: 🔶 高度 | 直接影响 SWE.4 证据强度

**现状**：
- `coverage-review` 步骤存在但依赖人工审查
- CI Layer 1 有 `coverage` 阶段但未说明实际工具
- 四轮审查专门扣 -1 分
- C 单元测试框架已到 72 分，但没有覆盖率数据支撑

**审计师会问**：
> "你们做单元测试但告诉我覆盖率是多少？语句覆盖？分支覆盖？MC/DC？"

**核心问题**：不能只用"我们做了"来证明 SWE.4。ASPICE 要求可量化的验证结果。C 单元测试框架已经到位 + Unity 已集成，差距只在 gcov/lcov 解析和报告一步。

**建议**：
- P0：GCC 编译时加 `--coverage` flag → 自动生成 `.gcda`/`.gcno` 文件
- P1：CI 中运行 `lcov --capture` + `genhtml` → 生成 HTML 覆盖率报告
- P2：coverage-review 步骤自动读取覆盖率阈值，低于阈值则阻断 Pipeline

---

## 5️⃣ 综合审计意见

| 维度 | 评分 | CL1 | CL2 |
|:-----|:----:|:---:|:---:|
| SWE.1 需求获取 | ✅ | ✅ | ❌ |
| SWE.2 架构设计 | ✅ | ✅ | ❌ |
| SWE.3 详细设计 | ✅ | ✅ | ❌ |
| SWE.4 单元验证 | ✅ 部分 | ✅ | ❌ |
| SWE.5 集成验证 | ✅ | ✅ | ❌ |
| SWE.6 合格性验证 | ✅ 部分 | ✅ | ❌ |
| **整体就绪度** | **85/100** | **CL1: YES ✅** | **CL2: NO ❌** |

### CL1 结论：✅ **可以过**

审计师会提整改项（三大 Gap 中的非致命项），但不会因为架构性缺陷否决 CL1。

**加分点**：23 步完整 V-Model 对齐、四个嵌入式专项审查（linker/startup/RTOS/memory）、C 单元测试三层 runner、LRM/LRT 追溯引擎、CI 四层递进式验证、MISRA 合规审查。

### CL2 结论：❌ **不能过，差得远**

不是修补一两个功能就能解决的问题。度量体系需要**数周的跨 Sprint 数据积累**。建议团队在 CL1 认证后，花 2 个 Sprint 专门攻克 CL2 度量基线。

---

### 老陈最后的话 👨‍🏫

23 步 Pipeline 是我在多个项目里看到的最完整的 ASPICE 对齐实现之一——尤其嵌入式专业的四个审查步骤（linker/startup/RTOS/memory），很多拿到 CL2 认证的项目都没做到这个深度。

但你问我 CL2 能不能过，我的答案很简单：

> **没有数据，就没有管理；没有管理，就没有 CL2。**

CL1 证明了你会做事。CL2 证明了你能持续做好事。数据才是桥梁。

去把 gcov/lcov 接上，让文档和代码同步自动化，跑两个 Sprint 积累数据——然后我来做 CL2 审计。👍

---

*审计人: 老陈 👨‍🏫 | 基于 PIPELINE_STEPS 23 步 + CI 4 层 + expert-pipeline-assessment4（85 分）*
*报告路径: `reports/aspice-audit-report.md`*
