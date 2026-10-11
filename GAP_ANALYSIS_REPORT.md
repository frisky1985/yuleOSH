# 🔍 yuleOSH ASPICE Compliance Gap Check

> **项目**: `.`
> **标准**: ASPICE v3.1
> **生成时间**: 2026-10-11T10:11:40.716854

---

## 📊 概要

| 指标 | 数量 |
|:-----|-----:|
| 总 BP 数 | 46 |
| ✅ 完全就绪 | 10 |
| ⚠️  部分就绪 | 8 |
| ❌ 缺失/未开始 | 28 |

🚩 **36 个 Base Practice 尚待补齐** — 详见下方逐项检查

---

## MAN.1: Project Management
> Plan, monitor, and control the project to deliver the product within
budget, schedule, and quality constraints.

**状态**: 2/2 BP 尚待补齐

### MAN.1.BP1: Define project plan

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Project plan with schedule
- Check: A project plan with schedule is defined (no docs/project-plan.md found)

**✅ 修复步骤**:

- 📄 创建 `docs/project-plan.md`，含进度计划与里程碑
- 🔖 定义 WBS 分解、出口准则与负责人

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.1.BP2: Monitor project progress

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Project status records
- Check: Project progress is monitored against the project plan (no docs/project-plan.md found)

**✅ 修复步骤**:

- 📊 在 `docs/project-plan.md` 记录进度跟踪与偏差
- 🔄 定期更新项目状态，对比计划与实际

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MAN.2: Requirements Management
> Elicit, document, and manage requirements and their changes under
configuration control.

**状态**: 1/2 BP 尚待补齐

### MAN.2.BP1: Manage requirements baseline

**状态**: ✅ 已就绪 (1/1)

### MAN.2.BP2: Manage requirement changes

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Requirement version records
- Check: Requirement changes are traced and versioned (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📊 记录需求变更历史与版本信息
- 🔗 需求变更追溯至受影响的设计、代码与测试

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MAN.3: Risk Management
> Identify, assess, and treat risks throughout the project lifecycle.

**状态**: 2/2 BP 尚待补齐

### MAN.3.BP1: Identify risks

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Risk register
- Check: Risks are identified and recorded in a risk register (no docs/risk-register.md found)

**✅ 修复步骤**:

- 📄 创建 `docs/risk-register.md`，记录已识别风险
- 🔖 每个风险含 ID、描述、可能性、影响与缓解措施

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.3.BP2: Assess and treat risks

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Risk treatment records
- Check: Risks are assessed and treatment tracked (no docs/risk-register.md found)

**✅ 修复步骤**:

- 📊 在 `docs/risk-register.md` 记录风险评估与处置进展
- 🔄 定期审查风险登记册，更新状态

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SUP.1: Quality Assurance
> Provide assurance that work products and processes conform to requirements
and plans through independent quality assurance activities.

**状态**: 3/3 BP 尚待补齐

### SUP.1.BP1: Define quality assurance approach

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Quality assurance plan
- Check: A quality assurance plan is defined and approved (no QA plan / audit records found)

**✅ 修复步骤**:

- 📄 创建 `docs/qa-plan.md`，定义质量保证计划（评审、审计、门禁）
- 🔖 明确 QA 角色、审计频率与出口准则

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SUP.1.BP2: Perform quality assurance audits

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Check: Quality assurance audits are performed and recorded (no QA plan / audit records found)

**✅ 修复步骤**:

- 📋 在 `.osh/ci/qa-audit.json` 记录 QA 审计结果
- 🔄 每个里程碑至少执行一次独立 QA 审计

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SUP.1.BP3: Verify work products

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Work product review records
- Check: Work products are reviewed per the defined process (no substantive review record found)

**✅ 修复步骤**:

- 📝 在 `docs/review-records.md` 记录工作产品评审结果
- ✅ 评审发现项跟踪至闭环

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SUP.10: Change Request Management
> Manage change requests from identification through analysis, decision,
and implementation.

**状态**: 2/2 BP 尚待补齐

### SUP.10.BP1: Identify change requests

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Change request log
- Check: Change requests are identified and recorded (no change-request records found)

**✅ 修复步骤**:

- 📄 创建 `docs/change-requests.md`，记录变更请求
- 🔖 每个 CR 分配唯一 ID、标题、状态

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SUP.10.BP2: Analyze and decide change requests

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Change request analysis records
- Check: Change requests are analyzed and status tracked (no change-request records found)

**✅ 修复步骤**:

- 📊 在 `docs/change-requests.md` 记录 CR 分析与决策
- ✅ 变更实施后更新状态并追溯至受影响的工作产品

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SUP.8: Configuration Management
> Establish and apply configuration management for the identified
configuration items throughout the project lifecycle.

**状态**: 0/2 BP 尚待补齐

### SUP.8.BP1: Establish configuration management

**状态**: ✅ 已就绪 (1/1)

### SUP.8.BP2: Baseline and release

**状态**: ✅ 已就绪 (1/1)

---

## SUP.9: Problem Resolution Management
> Identify, analyze, and resolve problems and defects systematically.

**状态**: 2/2 BP 尚待补齐

### SUP.9.BP1: Identify and analyze problems

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Issue/defect tracking log
- Check: Problems and defects are identified and tracked (no problem/issue tracking records found)

**✅ 修复步骤**:

- 📄 创建 `docs/known-issues.md`，记录问题与缺陷
- 🔖 每个问题分配唯一 ID、描述、严重度与状态

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SUP.9.BP2: Resolve problems

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Issue closure records
- Check: Problem resolution is recorded with closure evidence (no problem/issue tracking records found)

**✅ 修复步骤**:

- ✅ 在 `docs/known-issues.md` 记录问题修复与关闭证据
- 🔄 定期审查未关闭问题，推动闭环

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.1: Software Requirements Analysis
> Transform system requirements into a structured set of software requirements.

**状态**: 3/3 BP 尚待补齐

### SWE.1.BP1: Specify software requirements

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Software Requirements Specification (SRS)
- Missing evidence: Alternative requirements document
- Check: Requirements are traced to system requirements (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📄 创建 `docs/software-requirements.md` 或 `docs/requirements.md`
- 🔖 每条需求分配唯一标识符（REQ-xxx），包含 SHALL 语句
- 🔗 将每条需求追溯至系统需求

**💡 相关 CLI 命令**:

- `yuleosh spec validate docs/requirements.md` — 验证需求文件
- 查阅 `yuleosh --help` 获取全部命令

### SWE.1.BP2: Structure software requirements

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Structured specs directory
- Check: Requirements are organized by functional area (no functional-area grouping found)

**✅ 修复步骤**:

- 📂 在 `specs/` 目录下按功能区域组织需求文件
- 🏷️  为每条需求定义属性（优先级、状态）

**💡 相关 CLI 命令**:

- `yuleosh spec diff old.md new.md` — 对比需求变更
- 查阅 `yuleosh --help` 获取全部命令

### SWE.1.BP3: Evaluate impact of requirements

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Impact analysis document
- Check: Changes to requirements trigger impact analysis (no substantive impact analysis found)
- Check: Impact analysis covers schedule, resources, and risks (no substantive impact analysis found)

**✅ 修复步骤**:

- 📝 创建 `docs/impact-analysis.md`，记录变更影响分析
- 📊 每次需求变更时更新影响分析，覆盖进度、资源和风险

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.2: Software Architectural Design
> Establish a software architectural design that identifies components,
their interfaces, and data flow.

**状态**: 3/3 BP 尚待补齐

### SWE.2.BP1: Develop software architecture

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Software architecture document
- Missing evidence: Alternative architecture document
- Check: Architecture covers all software requirements (no substantive architecture doc found)
- Check: Architecture defines component boundaries and interfaces (no substantive architecture doc found)

**✅ 修复步骤**:

- 🏗️  创建 `docs/architecture.md` 或 `ARCHITECTURE.md`，覆盖全部软件需求
- 🧩 明确组件边界和接口定义

**💡 相关 CLI 命令**:

- `yuleosh pipeline run specs/spec.md` — 生成架构分析
- 查阅 `yuleosh --help` 获取全部命令

### SWE.2.BP2: Define interfaces

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: All external interfaces are defined
- Check: Interface specifications include data types and range

**✅ 修复步骤**:

- 📐 在 `include/` 目录中定义外部接口的头文件
- 📏 接口规范中包括数据类型和范围定义

**💡 相关 CLI 命令**:

- `yuleosh review task interface` — 审查接口设计
- 查阅 `yuleosh --help` 获取全部命令

### SWE.2.BP3: Verify architecture

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Architecture review record
- Check: Architecture review is conducted and documented (no substantive architecture doc found)
- Check: Review findings are tracked to closure (no substantive review record found)

**✅ 修复步骤**:

- 🔍 创建 `docs/architecture-review.md`，记录架构审查过程
- ✅ 审查发现项需跟踪至闭环

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.3: Software Detailed Design and Unit Construction
> Develop a detailed design for each software component and construct units.

**状态**: 2/3 BP 尚待补齐

### SWE.3.BP1: Develop detailed design

**状态**: ✅ 已就绪 (3/3)

### SWE.3.BP2: Define unit test cases

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Check: Test cases are traceable to requirements (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 🧪 在 `tests/` 目录为每个软件单元创建单元测试
- 🔀 测试覆盖正常、边界和错误条件
- 🔗 测试用例需可追溯至需求

**💡 相关 CLI 命令**:

- `yuleosh test c --create-suite` — 创建 C 单元测试脚手架
- 查阅 `yuleosh --help` 获取全部命令

### SWE.3.BP3: Verify detailed design

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Design review record
- Check: Design review is conducted per component (no substantive review record found)

**✅ 修复步骤**:

- 📋 创建 `docs/design-review.md`，记录每个组件的设计审查
- ✅ 审查覆盖正确性、一致性和可测试性

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.4: Software Unit Verification
> Verify software units against the detailed design and requirements.

**状态**: 1/3 BP 尚待补齐

### SWE.4.BP1: Perform unit verification

**状态**: ✅ 已就绪 (3/3)

### SWE.4.BP2: Establish bidirectional traceability

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Each requirement is traced to unit tests (matrix exists but <60% requirements traced to tests)
- Check: Traceability matrix is maintained and current (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📎 创建需求→单元测试的追溯矩阵（运行 `yuleosh evidence pack`）
- 🔄 保持追溯矩阵最新，每次需求变更后重新生成

**💡 相关 CLI 命令**:

- `yuleosh traceability matrix` — 生成追溯矩阵
- 查阅 `yuleosh --help` 获取全部命令

### SWE.4.BP3: Evaluate unit verification results

**状态**: ✅ 已就绪 (2/2)

---

## SWE.5: Software Integration and Integration Test
> Integrate software units and verify the integrated software against
the architecture and requirements.

**状态**: 2/3 BP 尚待补齐

### SWE.5.BP1: Develop integration strategy

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Integration strategy document
- Check: Integration sequence is defined and justified (CI results exist but no integration pass evidence)
- Check: Stubs/drivers are identified (no stubs/drivers in integration strategy)

**✅ 修复步骤**:

- 📄 创建 `docs/integration-strategy.md`，定义集成序列
- 🧩 识别所需的桩/驱动（stubs/drivers）

**💡 相关 CLI 命令**:

- `yuleosh coverage c` — 查看集成覆盖率
- 查阅 `yuleosh --help` 获取全部命令

### SWE.5.BP2: Integrate software units

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Integration builds succeed (CI results exist but no integration pass evidence)
- Check: Integration follows the defined strategy (CI results exist but no integration pass evidence)

**✅ 修复步骤**:

- 🔧 确保集成构建每次成功
- 📋 遵循已定义的集成策略进行集成

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SWE.5.BP3: Perform integration tests

**状态**: ✅ 已就绪 (3/3)

---

## SWE.6: Software Qualification Test
> Test the complete software against software requirements in the target
environment or a simulated environment.

**状态**: 3/3 BP 尚待补齐

### SWE.6.BP1: Develop qualification test strategy

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Qualification test strategy
- Check: Qualification test scope covers all requirements (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)
- Check: Acceptance criteria are defined for each requirement (no substantive acceptance matrix)

**✅ 修复步骤**:

- 📄 创建 `docs/qualification-strategy.md`，覆盖所有需求
- 🎯 为每条需求定义验收标准

**💡 相关 CLI 命令**:

- `yuleosh ci run 3` — 运行合格性测试层
- 查阅 `yuleosh --help` 获取全部命令

### SWE.6.BP2: Perform qualification tests

**状态**: ❌ 缺失 (2/3 项未通过)

**❌ 缺失项**:

- Missing evidence: SIL/HIL test results
- Check: All qualification tests pass (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)
- Check: Tests are executed in target or equivalent environment (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)

**✅ 修复步骤**:

- 🧪 运行全部合格性测试并确认通过
- 🎯 在目标环境或等效环境中执行测试
- 📦 归档测试证据（运行 `yuleosh audit evidence`）

**💡 相关 CLI 命令**:

- `yuleosh audit evidence` — 归档测试证据
- 查阅 `yuleosh --help` 获取全部命令

### SWE.6.BP3: Establish traceability

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Check: Qualification tests are traceable to requirements (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📎 创建需求→合格性测试的追溯（验收矩阵）
- 📊 运行 `yuleosh evidence pack` 生成需求覆盖率报告
- 🔍 标识并记录覆盖缺口

**💡 相关 CLI 命令**:

- `yuleosh evidence pack` — 生成完整证据包
- 查阅 `yuleosh --help` 获取全部命令

---

## SYS.1: System Requirements Analysis
> Transform stakeholder requirements into a structured set of system
requirements, establishing the top of the V-model left branch.

**状态**: 3/3 BP 尚待补齐

### SYS.1.BP1: Specify system requirements

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Check: System requirements are traced to stakeholder/source requirements (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.1.BP2: Structure system requirements

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Check: Requirements are organized by functional area (no functional-area grouping found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.1.BP3: Evaluate impact of system requirements

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Check: Changes to system requirements trigger impact analysis (no substantive impact analysis found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SYS.2: System Architectural Design
> Establish a system architectural design that identifies system elements,
their interfaces, and data flow.

**状态**: 1/3 BP 尚待补齐

### SYS.2.BP1: Develop system architecture

**状态**: ✅ 已就绪 (2/2)

### SYS.2.BP2: Define system interfaces

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: All external and internal interfaces are defined
- Check: Interface specifications include data types and range

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.2.BP3: Verify system architecture

**状态**: ✅ 已就绪 (1/1)

---

## SYS.3: System Verification
> Verify the system design against system requirements (verification plan
and verification cases for the system element level).

**状态**: 2/2 BP 尚待补齐

### SYS.3.BP1: Develop system verification strategy

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Verification scope covers all system requirements (docs/system-verification.md covers only 0/20 system requirements)
- Check: Acceptance criteria are defined for each requirement (no substantive acceptance matrix)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.3.BP2: Perform system verification

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Check: System verification cases are executed and documented (no system-level execution record — SIL/HIL or system test results required)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SYS.4: System Integration
> Integrate system elements and verify the integrated system against the
system architecture and system requirements.

**状态**: 2/3 BP 尚待补齐

### SYS.4.BP1: Develop system integration strategy

**状态**: ✅ 已就绪 (2/2)

### SYS.4.BP2: Integrate system elements

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Check: Integration builds succeed (no system-level integration execution record — SIL/HIL or system integration test results required)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.4.BP3: Perform system integration tests

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Check: Integration tests verify data flow between system elements (no system-level test execution record — SIL/HIL or system integration test results required)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SYS.5: System Validation (Confirmation)
> Validate the integrated system in the target environment (or representative
environment) to confirm it satisfies stakeholder requirements.

**状态**: 2/2 BP 尚待补齐

### SYS.5.BP1: Develop system validation strategy

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Validation scope covers stakeholder requirements (docs/system-validation.md covers only 0/20 system requirements)
- Check: Acceptance criteria are defined (no substantive acceptance matrix)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SYS.5.BP2: Perform system validation

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: System validation is executed in target or representative environment (no system-level execution record — SIL/HIL or system test results required)
- Check: Validation results are documented and traced to requirements (matrix exists but <60% requirements traced to tests)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## 🚀 快速启动

```bash
# 生成证据包（补齐多数 BP 证据）
yuleosh evidence pack

# 生成 CL2 审计证据包
yuleosh audit evidence

# 查看覆盖趋势
yuleosh coverage trend

# 查看 MISRA 违规趋势
yuleosh misra trend

# 查看 KPI 仪表盘
yuleosh kpi status
```

---
*报告由 yuleOSH ASPICE Gap Check 生成*