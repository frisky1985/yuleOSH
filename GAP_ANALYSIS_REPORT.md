# 🔍 yuleOSH ASPICE Compliance Gap Check

> **项目**: `.`
> **标准**: ASPICE v3.1
> **生成时间**: 2026-11-10T12:40:58.460987

---

## 📊 概要

| 指标 | 数量 |
|:-----|-----:|
| 总 BP 数 | 116 |
| ✅ 完全就绪 | 32 |
| ⚠️  部分就绪 | 14 |
| ❌ 缺失/未开始 | 70 |

🚩 **84 个 Base Practice 尚待补齐** — 详见下方逐项检查

---

## ACQ.4: Supplier Monitoring
> Monitor suppliers against agreed requirements and take corrective action
when commitments are not met. The supplier inventory is seeded from the
project's declared third-party dependencies; assessments are human decisions.

**状态**: 4/4 BP 尚待补齐

### ACQ.4.BP1: Establish supplier monitoring

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Supplier register with unique identifiers and scan sources
- Check: Every supplier is uniquely identified by an ACQ-xxx ID (no supplier register / monitoring report found)
- Check: The register records which sources were scanned for suppliers (no supplier register / monitoring report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### ACQ.4.BP2: Agree on supplier requirements

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Requirement, scope and assessment status per supplier
- Check: Each supplier records its version requirement and scope (no supplier register / monitoring report found)
- Check: Supplier status comes from a controlled vocabulary (no supplier register / monitoring report found)
- Check: Auto-detected suppliers stay pending until a human assesses them (no supplier register / monitoring report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### ACQ.4.BP3: Monitor suppliers

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Current status and monitoring method per supplier
- Check: The report lists every registered supplier with its current status (no supplier register / monitoring report found)
- Check: Pending suppliers are visible, not silently treated as approved (no supplier register / monitoring report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### ACQ.4.BP4: Take corrective actions

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Corrective actions for suppliers that do not meet requirements
- Check: A rejected supplier carries a corrective action (no supplier register / monitoring report found)
- Check: Corrective actions are tracked in the supplier report (no supplier register / monitoring report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## HWE.1: Hardware Requirements Analysis
> Identify the hardware scope and specify hardware requirements for every
item in it. Scope is detected from objective file signals (linker scripts,
CubeMX configs, board directories, CAN matrices, startup code); an empty
result is recorded as such, never silently filled in.

**状态**: 4/4 BP 尚待补齐

### HWE.1.BP1: Identify hardware scope

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Hardware item register with unique identifiers and scan sources
- Check: Every hardware item is uniquely identified by a HWE-xxx ID (no hardware register / requirements found)
- Check: The hardware register records which sources were scanned (no hardware register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.1.BP2: Specify hardware requirements

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Hardware requirements covering every registered item
- Check: Hardware requirements are documented for every registered hardware item (no hardware register / requirements found)
- Check: Hardware scope absence is recorded explicitly, never inferred (no hardware register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.1.BP3: Classify hardware items

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Kind and status from controlled vocabularies per item
- Check: Hardware item kind and status come from controlled vocabularies (no hardware register / requirements found)
- Check: Auto-detected hardware items stay pending until a human analyzes them (no hardware register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.1.BP4: Maintain hardware traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from hardware items to design and verification records
- Check: Hardware items are linked to downstream hardware records (no hardware register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## HWE.2: Hardware Design
> Develop a hardware design that covers every registered hardware item and
records constraints, resource allocation and hardware-software partitioning.

**状态**: 4/4 BP 尚待补齐

### HWE.2.BP1: Develop hardware design

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Hardware design covering every registered item
- Check: The hardware design covers every registered hardware item (no hardware design document found)
- Check: Hardware design constraints are recorded (no hardware design document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.2.BP2: Allocate hardware resources

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Resource allocation and hardware-software partitioning
- Check: Hardware design records resource allocation and hardware-software partitioning (no hardware design document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.2.BP3: Keep design consistent with scope

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Design coverage per register item, or explicit empty-scope statement
- Check: The hardware design names each registered hardware item by ID (no hardware design document found)
- Check: A hardware design with empty scope states it explicitly (no hardware design document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.2.BP4: Maintain design traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from design to register and implementation records
- Check: The hardware design points to the register and implementation records (no hardware design document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## HWE.3: Hardware Implementation
> Track hardware implementation against the design: build outputs are listed
with path, size and digest, and every listed output must exist on disk.

**状态**: 4/4 BP 尚待补齐

### HWE.3.BP1: Record build outputs

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Build outputs with path, size and digest
- Check: Hardware build outputs are listed with path and digest (no hardware implementation report found)
- Check: Every listed hardware build output exists on disk (no hardware implementation report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.3.BP2: Track implementation per item

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Implementation status per registered hardware item
- Check: Hardware implementation status is tracked per registered item (no hardware implementation report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.3.BP3: Detect build outputs objectively

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Build outputs found by filesystem scan, not declared from memory
- Check: Hardware build outputs come from a filesystem scan with recorded patterns (no hardware implementation report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.3.BP4: Maintain implementation traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from implementation to design and verification records
- Check: The hardware implementation report maintains links to related hardware records (no hardware implementation report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## HWE.4: Hardware Verification
> Record hardware verification per registered item. An item may only be
marked verified with a cited evidence file that exists on disk and names
the item; the pipeline never marks anything verified on its own.

**状态**: 4/4 BP 尚待补齐

### HWE.4.BP1: Record verification status

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Verification status per registered hardware item
- Check: Hardware verification status is recorded per registered item (no hardware verification report + register found)
- Check: Hardware verification reports absence of scope explicitly (no hardware verification report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.4.BP2: Require verification evidence

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Cited evidence file per verified item
- Check: A hardware item verification claim requires cited evidence on disk (no hardware verification report + register found)
- Check: Hardware verification evidence is re-opened and re-checked by the gate (no hardware verification report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.4.BP3: No self-assigned verdicts

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Unverified items are reported as unverified
- Check: Hardware verification marks items without evidence as unverified (no hardware verification report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### HWE.4.BP4: Maintain verification traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from verification to register and implementation records
- Check: The hardware verification report maintains links to related hardware records (no hardware verification report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MAN.1: Project Management
> Plan, monitor, and control the project to deliver the product within
budget, schedule, and quality constraints.

**状态**: 0/2 BP 尚待补齐

### MAN.1.BP1: Define project plan

**状态**: ✅ 已就绪 (1/1)

### MAN.1.BP2: Monitor project progress

**状态**: ✅ 已就绪 (1/1)

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
- Check: Requirement changes are traced and versioned (no substantive traceability matrix)

**✅ 修复步骤**:

- 📊 记录需求变更历史与版本信息
- 🔗 需求变更追溯至受影响的设计、代码与测试

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MAN.3: Project Management
> Plan, monitor, and control the project. Milestones come only from the real
milestone list; completed milestones must carry completion evidence.

**状态**: 0/4 BP 尚待补齐

### MAN.3.BP1: Define project plan

**状态**: ✅ 已就绪 (1/1)

### MAN.3.BP2: Monitor project progress

**状态**: ✅ 已就绪 (1/1)

### MAN.3.BP3: Define and track milestones

**状态**: ✅ 已就绪 (1/1)

### MAN.3.BP4: Manage schedule deviations

**状态**: ✅ 已就绪 (1/1)

---

## MAN.5: Risk Management
> Identify, analyze, prioritize and monitor risks continuously. Risks are
sourced from objective signals (failing measures, failed pipeline steps)
and human-maintained entries; risk status is never inferred automatically.

**状态**: 4/4 BP 尚待补齐

### MAN.5.BP1: Establish risk management scope

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Risk management scope, responsibilities and escalation path
- Check: Scope covers the engineering activities before product release (no release plan / manifest with digests found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.5.BP2: Identify and analyze risks

**状态**: ⚠️  部分就绪 (1/4 项未通过)

**❌ 缺失项**:

- Missing evidence: Risk register with likelihood, impact and score per risk
- Check: Scan sources are recorded; an empty register must state what was scanned (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.5.BP3: Define risk response measures

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Response strategy, mitigation and owner per risk
- Check: Response is one of avoid/mitigate/transfer/accept (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.5.BP4: Monitor and escalate risks

**状态**: ⚠️  部分就绪 (1/5 项未通过)

**❌ 缺失项**:

- Missing evidence: Risk status, open high risks and escalation items
- Check: Triaged open high risks carry a review due date (YYYY-MM-DD) (no substantive review record found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MAN.6: Measurement
> Collect, store, analyze and report measurement data to support
management decisions. Measures shall be traceable to their data
sources; absent data must be reported as absent rather than inferred.

**状态**: 5/5 BP 尚待补齐

### MAN.6.BP1: Establish measurement objectives

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Measurement objectives aligned with project goals
- Check: Objectives state what decision each measure supports (unknown check type — not recognized)
- Check: Objectives cover process and product quality (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.6.BP2: Define measures

**状态**: ❌ 缺失 (2/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Measure definitions with data source, frequency, threshold
- Check: Each measure declares its data source and collection frequency (unknown check type — not recognized)
- Check: Thresholds come from a single source of truth (ci.kpi) (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.6.BP3: Collect and store measurement data

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Raw measurement records produced by the pipeline
- Check: Data is produced by pipeline steps, not entered by hand (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.6.BP4: Analyze measurement data

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Threshold verdicts, trend analysis and corrective actions
- Check: Every measure is marked PASS, FAIL or no-data (unknown check type — not recognized)
- Check: No-data measures are never inferred as passing (unknown check type — not recognized)
- Check: FAIL measures carry corrective actions (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MAN.6.BP5: Report measurement results

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Measurement report shared with management
- Check: Report states the collection timestamp (unknown check type — not recognized)
- Check: Report is traceable to the measurement plan (no substantive traceability matrix)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MLE.1: Machine Learning Requirements Analysis
> Identify the machine learning scope (models, training scripts, datasets)
from objective file signals and specify ML requirements for every item.
An empty result is recorded as such, never silently filled in.

**状态**: 4/4 BP 尚待补齐

### MLE.1.BP1: Identify machine learning scope

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: ML item register with unique identifiers and scan sources
- Check: Every machine learning item is uniquely identified by an MLE-xxx ID (no machine learning register / requirements found)
- Check: The machine learning register records which sources were scanned (no machine learning register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.1.BP2: Specify machine learning requirements

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: ML requirements covering every registered item
- Check: Machine learning requirements are documented per registered item (no machine learning register / requirements found)
- Check: Absence of machine learning scope is recorded explicitly (no machine learning register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.1.BP3: Classify machine learning items

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Kind and status from controlled vocabularies per item
- Check: Machine learning item kind and status come from controlled vocabularies (no machine learning register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.1.BP4: Maintain machine learning traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from ML items to approach, training and evaluation records
- Check: The machine learning register maintains links to downstream records (no machine learning register / requirements found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MLE.2: Machine Learning Approach
> Define the machine learning approach: model selection with rationale,
data strategy, and metric targets with resource budgets — covering every
registered ML item.

**状态**: 4/4 BP 尚待补齐

### MLE.2.BP1: Define machine learning approach

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Model selection, data strategy and metric budgets
- Check: The machine learning approach records model selection, data strategy and metric budgets (no machine learning approach document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.2.BP2: Cover every registered item

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Approach coverage per register item, or explicit empty-scope statement
- Check: The machine learning approach covers every registered item (no machine learning approach document found)
- Check: A machine learning approach with empty scope states it explicitly (no machine learning approach document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.2.BP3: State metric targets and budgets

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Metric targets and resource budgets section
- Check: The machine learning approach states metric targets and resource budgets (no machine learning approach document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.2.BP4: Maintain approach traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from approach to register and training records
- Check: The machine learning approach points to the register and training records (no machine learning approach document found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MLE.3: Machine Learning Training
> Record training runs. Training sources come from a filesystem scan;
metrics are written by humans from real training output and are preserved
across runs — the report never generates metric values on its own.

**状态**: 4/4 BP 尚待补齐

### MLE.3.BP1: List training sources

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Training scripts found by filesystem scan
- Check: Training sources are listed with paths that exist on disk (no machine learning training report found)
- Check: Training sources come from a filesystem scan, not from memory (no machine learning training report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.3.BP2: Record training outcomes

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Human-recorded training records preserved across runs
- Check: Training metrics are recorded by humans, never fabricated (no machine learning training report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.3.BP3: Preserve training records

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Training records section survives regeneration
- Check: Training records are preserved when the training report regenerates (no machine learning training report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.3.BP4: Maintain training traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from training to approach and evaluation records
- Check: The training report maintains links to related machine learning records (no machine learning training report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## MLE.4: Machine Learning Testing
> Record model evaluation per registered model. A model may only be marked
evaluated when docs/ml-eval-<id>.yaml exists with non-empty metrics; the
review re-parses every cited file.

**状态**: 4/4 BP 尚待补齐

### MLE.4.BP1: Record evaluation status

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Evaluation status per registered model
- Check: Model evaluation status is recorded per registered model (no machine learning evaluation report + register found)
- Check: Models without evaluation evidence are reported as not evaluated (no machine learning evaluation report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.4.BP2: Require evaluation evidence

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Evaluation evidence file with non-empty metrics per evaluated model
- Check: A model is marked evaluated only with cited metric evidence on disk (no machine learning evaluation report + register found)
- Check: Model evaluation evidence is re-parsed and re-checked by the gate (no machine learning evaluation report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.4.BP3: No self-assigned verdicts

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: The pipeline never evaluates a model on its own
- Check: Model evaluation verdicts come from evidence files, never from inference (no machine learning evaluation report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### MLE.4.BP4: Maintain evaluation traceability

**状态**: ❌ 缺失 (1/1 项未通过)

**❌ 缺失项**:

- Missing evidence: Links from evaluation to register and training records
- Check: The model evaluation report points to the register records (no machine learning evaluation report + register found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## PIM.3: Process Improvement
> Identify and implement improvements to the processes used by the project.
Improvement items are derived only from objective inputs (failing measures
and open high-severity items); an empty input set is reported as such.

**状态**: 4/4 BP 尚待补齐

### PIM.3.BP1: Establish process improvement

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Improvement scope, flow, roles and escalation
- Check: The plan states which objective inputs may raise improvements (no process improvement evidence found)
- Check: Roles and escalation path for process improvement are defined (no process improvement evidence found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### PIM.3.BP2: Evaluate processes

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Improvement inputs from measurement and high-severity records
- Check: Improvement inputs record which sources were read (no process improvement evidence found)
- Check: No improvement input means no improvement item; nothing is fabricated (no process improvement evidence found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### PIM.3.BP3: Plan improvements

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Improvement register with identifiers, source and objective
- Check: Every improvement is uniquely identified by a PIM-xxx ID (no process improvement evidence found)
- Check: Each improvement records its source and objective (no process improvement evidence found)
- Check: Improvement status comes from a controlled vocabulary (no process improvement evidence found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### PIM.3.BP4: Implement and monitor improvements

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Improvement status and owners
- Check: Triaged in-progress improvements carry an owner and a due date (no process improvement evidence found)
- Check: Auto-derived improvements without an owner are reported as pending (no process improvement evidence found)
- Check: Improvement status is changed by people only (no process improvement evidence found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## REU.2: Reuse Management
> Identify reuse opportunities and decide, with recorded rationale, which
components are reused. Automatic identification produces candidates only;
a human decides reuse.

**状态**: 4/4 BP 尚待补齐

### REU.2.BP1: Identify reuse opportunities

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Reuse register with unique identifiers and scan sources
- Check: Every reuse candidate is uniquely identified by a REU-xxx ID (no reuse register / report found)
- Check: The register records which sources were scanned for reuse opportunities (no reuse register / report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### REU.2.BP2: Assess reuse candidates

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Kind, reuse status and rationale per component
- Check: Kind and reuse status come from controlled vocabularies (no reuse register / report found)
- Check: Rejecting reuse requires a documented rationale (no reuse register / report found)
- Check: Auto-detected reuse candidates stay pending until assessed (no reuse register / report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### REU.2.BP3: Integrate reused components

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Reuse decisions and status
- Check: Reuse decisions are recorded in the report (no reuse register / report found)
- Check: The pipeline never marks a component reused on its own (no reuse register / report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### REU.2.BP4: Report reuse status

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Reuse status report
- Check: The report lists every registered reuse candidate (no reuse register / report found)
- Check: Pending reuse candidates are reported as pending (no reuse register / report found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SPL.2: Product Release
> Assemble and approve a release from controlled work products. The release
manifest carries SHA-256 digests; approval is a human decision and defaults
to pending.

**状态**: 4/4 BP 尚待补齐

### SPL.2.BP1: Establish release plan

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Release scope, criteria and approval process
- Check: The release plan states the release version and scope (no release plan / manifest with digests found)
- Check: The release plan defines criteria including gate evidence and artifact digests (no release plan / manifest with digests found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SPL.2.BP2: Approve release

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Approval status recorded in the manifest
- Check: The release manifest approval status is one of pending/approved/rejected (no release plan / manifest with digests found)
- Check: The release manifest defaults to pending; only a human approves (no release plan / manifest with digests found)
- Check: A product release cannot be approved while hard gates failed or were not run (no release plan / manifest with digests found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SPL.2.BP3: Generate release package

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Artifact list with path and SHA-256 per file
- Check: Every release package artifact records a path and a SHA-256 digest (no release plan / manifest with digests found)
- Check: The release package artifact list comes from real files, not from memory (no release plan / manifest with digests found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SPL.2.BP4: Verify release

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Digest verification and gate snapshot
- Check: Stored release manifest digests are re-verified against the files on disk (no release plan / manifest with digests found)
- Check: The release manifest records the gate snapshot; missing evidence is not called green (no release plan / manifest with digests found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SUP.1: Quality Assurance
> Provide assurance that work products and processes conform to requirements
and plans through independent quality assurance activities. Audit records
come from real review/CI artifacts; an empty scan is recorded as such.

**状态**: 0/4 BP 尚待补齐

### SUP.1.BP1: Define quality assurance approach

**状态**: ✅ 已就绪 (1/1)

### SUP.1.BP2: Perform quality assurance audits

**状态**: ✅ 已就绪 (1/1)

### SUP.1.BP3: Verify work products

**状态**: ✅ 已就绪 (1/1)

### SUP.1.BP4: Track quality deviations

**状态**: ✅ 已就绪 (1/1)

---

## SUP.10: Change Request Management
> Manage change requests from identification through analysis, decision, and
implementation. Approved changes must carry a decision record; an empty
scan is recorded as such rather than filled with invented requests.

**状态**: 0/4 BP 尚待补齐

### SUP.10.BP1: Identify change requests

**状态**: ✅ 已就绪 (1/1)

### SUP.10.BP2: Analyze change requests

**状态**: ✅ 已就绪 (1/1)

### SUP.10.BP3: Track change status

**状态**: ✅ 已就绪 (1/1)

### SUP.10.BP4: Implement approved changes

**状态**: ✅ 已就绪 (1/1)

---

## SUP.8: Configuration Management
> Establish and apply configuration management for identified configuration
items. The baseline manifest records a SHA256 per item plus a manifest
digest that the review step recomputes.

**状态**: 0/4 BP 尚待补齐

### SUP.8.BP1: Establish configuration management

**状态**: ✅ 已就绪 (1/1)

### SUP.8.BP2: Identify configuration items

**状态**: ✅ 已就绪 (1/1)

### SUP.8.BP3: Baseline and release

**状态**: ✅ 已就绪 (1/1)

### SUP.8.BP4: Record configuration status

**状态**: ✅ 已就绪 (1/1)

---

## SUP.9: Problem Resolution Management
> Identify, analyze, and resolve problems and defects systematically. Issue
records come only from real structured logs; closed issues must carry a
closure note, otherwise the gate is RED.

**状态**: 0/4 BP 尚待补齐

### SUP.9.BP1: Identify and analyze problems

**状态**: ✅ 已就绪 (1/1)

### SUP.9.BP2: Analyze problems

**状态**: ✅ 已就绪 (1/1)

### SUP.9.BP3: Track issue status

**状态**: ✅ 已就绪 (1/1)

### SUP.9.BP4: Resolve problems

**状态**: ✅ 已就绪 (1/1)

---

## SWE.1: Software Requirements Analysis
> Transform system requirements into a structured set of software requirements.

**状态**: 2/3 BP 尚待补齐

### SWE.1.BP1: Specify software requirements

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Alternative requirements document
- Check: Requirements are traced to system requirements (no substantive traceability matrix)

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

**状态**: ✅ 已就绪 (2/2)

---

## SWE.2: Software Architectural Design
> Establish a software architectural design that identifies components,
their interfaces, and data flow.

**状态**: 1/3 BP 尚待补齐

### SWE.2.BP1: Develop software architecture

**状态**: ✅ 已就绪 (2/2)

### SWE.2.BP2: Define interfaces

**状态**: ✅ 已就绪 (2/2)

### SWE.2.BP3: Verify architecture

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

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

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Check: Unit tests exist for each software unit (591 test files but no passing-run evidence)
- Check: Test cases cover normal, boundary, and error conditions (591 test files but no passing-run evidence)
- Check: Test cases are traceable to requirements (no substantive traceability matrix)

**✅ 修复步骤**:

- 🧪 在 `tests/` 目录为每个软件单元创建单元测试
- 🔀 测试覆盖正常、边界和错误条件
- 🔗 测试用例需可追溯至需求

**💡 相关 CLI 命令**:

- `yuleosh test c --create-suite` — 创建 C 单元测试脚手架
- 查阅 `yuleosh --help` 获取全部命令

### SWE.3.BP3: Verify detailed design

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Design review is conducted per component (no substantive review record found)
- Check: Review covers correctness, consistency, and testability (591 test files but no passing-run evidence)

**✅ 修复步骤**:

- 📋 创建 `docs/design-review.md`，记录每个组件的设计审查
- ✅ 审查覆盖正确性、一致性和可测试性

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.4: Software Unit Verification
> Verify software units against the detailed design and requirements.

**状态**: 3/3 BP 尚待补齐

### SWE.4.BP1: Perform unit verification

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: CI test execution records
- Check: All unit tests pass (100% pass rate) (591 test files but no passing-run evidence)
- Check: Statement coverage ≥ 80%
- Check: Branch/condition coverage ≥ 70%

**✅ 修复步骤**:

- 🧪 运行全部单元测试并确认 100% 通过
- 📊 语句覆盖率 ≥ 80%（运行 coverage trend 检查）
- 🌿 分支/条件覆盖率 ≥ 70%
- ⚙️  在 `.yuleosh/ci/` 中配置 CI 执行记录

**💡 相关 CLI 命令**:

- `yuleosh coverage trend` — 查看测试覆盖率趋势
- 查阅 `yuleosh --help` 获取全部命令

### SWE.4.BP2: Establish bidirectional traceability

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Traceability matrix
- Check: Each requirement is traced to unit tests (no substantive traceability matrix)
- Check: Traceability matrix is maintained and current (no substantive traceability matrix)

**✅ 修复步骤**:

- 📎 创建需求→单元测试的追溯矩阵（运行 `yuleosh evidence pack`）
- 🔄 保持追溯矩阵最新，每次需求变更后重新生成

**💡 相关 CLI 命令**:

- `yuleosh traceability matrix` — 生成追溯矩阵
- 查阅 `yuleosh --help` 获取全部命令

### SWE.4.BP3: Evaluate unit verification results

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Evidence collection
- Check: Failed tests are analyzed and documented (591 test files but no passing-run evidence)
- Check: Regression test strategy is defined (591 test files but no passing-run evidence)

**✅ 修复步骤**:

- 📝 记录失败测试的分析结果和修复计划
- 🔄 定义回归测试策略（建议在 ci-config.yaml 中配置）

**💡 相关 CLI 命令**:

- `yuleosh audit evidence` — 收集审计证据
- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.5: Software Integration and Integration Test
> Integrate software units and verify the integrated software against
the architecture and requirements.

**状态**: 3/3 BP 尚待补齐

### SWE.5.BP1: Develop integration strategy

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

- Check: Integration sequence is defined and justified

**✅ 修复步骤**:

- 📄 创建 `docs/integration-strategy.md`，定义集成序列
- 🧩 识别所需的桩/驱动（stubs/drivers）

**💡 相关 CLI 命令**:

- `yuleosh coverage c` — 查看集成覆盖率
- 查阅 `yuleosh --help` 获取全部命令

### SWE.5.BP2: Integrate software units

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: CI integration records
- Check: Integration builds succeed
- Check: Integration follows the defined strategy

**✅ 修复步骤**:

- 🔧 确保集成构建每次成功
- 📋 遵循已定义的集成策略进行集成

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### SWE.5.BP3: Perform integration tests

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Integration test directory
- Missing evidence: Integration test results
- Check: Integration tests cover component interfaces (591 test files but no passing-run evidence)
- Check: Integration tests verify data flow between components (591 test files but no passing-run evidence)
- Check: All integration tests pass (591 test files but no passing-run evidence)

**✅ 修复步骤**:

- 🧪 在 `tests/integration/` 中创建集成测试
- 🔀 集成测试覆盖组件间接口和数据流
- ✅ 全部集成测试通过

**💡 相关 CLI 命令**:

- `yuleosh ci run 25` — 运行集成测试层
- 查阅 `yuleosh --help` 获取全部命令

---

## SWE.6: Software Qualification Test
> Test the complete software against software requirements in the target
environment or a simulated environment.

**状态**: 3/3 BP 尚待补齐

### SWE.6.BP1: Develop qualification test strategy

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Check: Qualification test scope covers all requirements (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)
- Check: Acceptance criteria are defined for each requirement (no substantive acceptance matrix)

**✅ 修复步骤**:

- 📄 创建 `docs/qualification-strategy.md`，覆盖所有需求
- 🎯 为每条需求定义验收标准

**💡 相关 CLI 命令**:

- `yuleosh ci run 3` — 运行合格性测试层
- 查阅 `yuleosh --help` 获取全部命令

### SWE.6.BP2: Perform qualification tests

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Qualification test results
- Missing evidence: SIL/HIL test results
- Check: All qualification tests pass (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)
- Check: Tests are executed in target or equivalent environment (no SIL/HIL results — unit tests do not qualify as target/equivalent-environment execution)
- Check: Resulting evidence is archived (no archived evidence found)

**✅ 修复步骤**:

- 🧪 运行全部合格性测试并确认通过
- 🎯 在目标环境或等效环境中执行测试
- 📦 归档测试证据（运行 `yuleosh audit evidence`）

**💡 相关 CLI 命令**:

- `yuleosh audit evidence` — 归档测试证据
- 查阅 `yuleosh --help` 获取全部命令

### SWE.6.BP3: Establish traceability

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Acceptance matrix
- Missing evidence: Requirement coverage report
- Check: Qualification tests are traceable to requirements (no substantive traceability matrix)
- Check: Coverage gaps are identified and documented

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

**状态**: 2/3 BP 尚待补齐

### SYS.1.BP1: Specify system requirements

**状态**: ⚠️  部分就绪 (1/3 项未通过)

**❌ 缺失项**:

- Check: System requirements are traced to stakeholder/source requirements (no substantive traceability matrix)

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

**状态**: ✅ 已就绪 (1/1)

---

## SYS.2: System Architectural Design
> Establish a system architectural design that identifies system elements,
their interfaces, and data flow.

**状态**: 0/3 BP 尚待补齐

### SYS.2.BP1: Develop system architecture

**状态**: ✅ 已就绪 (2/2)

### SYS.2.BP2: Define system interfaces

**状态**: ✅ 已就绪 (2/2)

### SYS.2.BP3: Verify system architecture

**状态**: ✅ 已就绪 (1/1)

---

## SYS.3: System Verification
> Verify the system design against system requirements (verification plan
and verification cases for the system element level).

**状态**: 2/2 BP 尚待补齐

### SYS.3.BP1: Develop system verification strategy

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

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

**状态**: ⚠️  部分就绪 (1/2 项未通过)

**❌ 缺失项**:

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
- Check: Validation results are documented and traced to requirements (no substantive traceability matrix)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

---

## VAL.1: Product Validation
> Confirm that the product fulfils its intended use in its intended
environment. Validation differs from verification: it answers
"did we build the right product", based on stakeholder needs rather
than on the specification alone.

**状态**: 4/4 BP 尚待补齐

### VAL.1.BP1: Develop validation measures and criteria

**状态**: ❌ 缺失 (2/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Validation plan with measures, environment and pass criteria
- Check: Each scenario declares target/equivalent environment and method (unknown check type — not recognized)
- Check: Pass criteria are measurable and reviewable (no substantive review record found)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### VAL.1.BP2: Validate product

**状态**: ❌ 缺失 (3/3 项未通过)

**❌ 缺失项**:

- Missing evidence: Validation report aggregated from real execution records
- Missing evidence: Raw validation execution records (result + evidence path)
- Check: Report only reflects recorded executions, no inferred pass (unknown check type — not recognized)
- Check: Every PASS entry carries a verifiable evidence path (unknown check type — not recognized)
- Check: Scenarios without records are reported as not executed (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### VAL.1.BP3: Establish bidirectional traceability

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Requirement <-> validation scenario traceability matrix
- Check: Every requirement maps to at least one validation scenario (unknown check type — not recognized)
- Check: Every scenario maps back to a requirement (no orphan scenario) (unknown check type — not recognized)

**✅ 修复步骤**:

- 📋 查看过程组文档，确认此 BP 的产出物
- 📎 检查 `.osh/evidence/` 中是否已有部分证据

**💡 相关 CLI 命令**:

- 查阅 `yuleosh --help` 获取全部命令

### VAL.1.BP4: Ensure consistency

**状态**: ❌ 缺失 (2/2 项未通过)

**❌ 缺失项**:

- Missing evidence: Consistency between validation criteria and requirements
- Check: Criteria are derived from the linked requirement (unknown check type — not recognized)
- Check: SYS.5 and SWE.6 evidence are referenced, not substituted (unknown check type — not recognized)

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