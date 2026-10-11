# SUP/MAN 证据产出指引

> **Document**: `docs/compliance/sup-man-evidence-guide.md`
> **Version**: 1.0.0
> **Status**: Active
> **Profile**: `aspice_support_mgmt_v3.1`

## 概述

本文档说明 yuleOSH 如何为 ASPICE v3.1 支持过程（SUP）与管理过程（MAN）的每个
Base Practice 产出合规证据。目标能力等级：**CL2（已管理）** 与 **CL3（已建立）**。

**反假绿原则**：yuleOSH 合规引擎仅在接受到真实项目产物时判 GREEN；无证据一律判
RED，绝不臆造通过状态。

---

## 评估域总览

| 过程域 | ID | 名称 | 证据函数 | 最低证据路径 |
|--------|------|------|----------|-------------|
| 支持过程 | SUP.1 | Quality Assurance | `_has_qa_records()` | `docs/qa-plan.md` |
| 支持过程 | SUP.8 | Configuration Management | `_has_vcs_baseline()` | `.git/` |
| 支持过程 | SUP.9 | Problem Resolution | `_has_issue_records()` | `docs/known-issues.md` |
| 支持过程 | SUP.10 | Change Request Mgmt | `_has_change_records()` | `docs/change-requests.md` |
| 管理过程 | MAN.1 | Project Management | `_file_has_content()` | `docs/project-plan.md` |
| 管理过程 | MAN.2 | Requirements Management | `_file_has_content()` | `docs/requirements.md` |
| 管理过程 | MAN.3 | Risk Management | `_file_has_content()` | `docs/risk-register.md` |

---

## SUP.1 — Quality Assurance

### BP1: Define quality assurance approach

**CL2 要求**：定义质量保证方法并经批准。

**yuleOSH 证据**：
- `docs/qa-plan.md`（≥100 字符实质性内容）
- 内容应包含：QA 目标、审计频率、评审准则、角色职责

**产出方式**：
```bash
# 手动创建或使用模板
yuleosh compliance init --template qa-plan
```

**CL3 增强**：QA 计划需与项目计划关联，并经配置管理基线化。

### BP2: Perform quality assurance audits

**CL2 要求**：执行 QA 审计并记录结果。

**yuleOSH 证据**（任一即可）：
- `.osh/ci/qa-audit.json` — CI 流水线自动生成的审计记录
- `.osh/ci/qa-audit-*.json` — 多次审计记录
- `docs/review-records.md` — 工作产品评审记录

**产出方式**：
```bash
# CI 流水线自动产出（推荐）
yuleosh pipeline run --qa-audit

# 或手动记录评审
yuleosh review record --task TASK-ID --result pass
```

### BP3: Verify work products

**CL2 要求**：按定义的过程评审工作产品。

**yuleOSH 证据**：
- `docs/review-records.md` — 评审记录
- `.osh/ci/review-*.json` — 自动化评审记录

---

## SUP.8 — Configuration Management

### BP1: Establish configuration management

**CL2 要求**：建立配置管理体系，识别配置项。

**yuleOSH 证据**：
- `.git/` 目录存在 — 证明项目已纳入版本控制

**产出方式**：
```bash
git init  # 或已存在的 git 仓库
```

**CL3 增强**：配置管理计划应定义分支策略、标签规范、基线策略。

### BP2: Baseline and release

**CL2 要求**：基线和发布受版本控制管理。

**yuleOSH 证据**：
- `releases/` 目录 — 发布基线
- Git tags — 版本标签

**产出方式**：
```bash
git tag -a v1.0.0 -m "Release 1.0.0"
mkdir -p releases/
yuleosh release create --version 1.0.0
```

---

## SUP.9 — Problem Resolution Management

### BP1: Identify and analyze problems

**CL2 要求**：识别并跟踪问题和缺陷。

**yuleOSH 证据**（任一即可）：
- `docs/known-issues.md`（≥100 字符）— 问题跟踪日志
- `.osh/ci/issue-*.json` — CI 生成的问题记录

**产出方式**：
```bash
# 手动维护
# docs/known-issues.md
# | ID | Title | Status | Severity | Created |
# |----|-------|--------|----------|---------|
# | I-001 | ... | Open | High | 2026-10-01 |

# 或从外部系统同步
yuleosh issue sync --from jira
```

### BP2: Resolve problems

**CL2 要求**：记录问题解决过程和关闭证据。

**yuleOSH 证据**：
- `docs/known-issues.md` 中包含 Closed/Resolved 状态的记录
- 关闭记录应包含：解决方案、验证结果、关闭日期

---

## SUP.10 — Change Request Management

### BP1: Identify change requests

**CL2 要求**：识别并记录变更请求。

**yuleOSH 证据**（任一即可）：
- `docs/change-requests.md`（≥100 字符）— 变更请求日志
- `.osh/ci/change-*.json` — CI 生成的变更记录

**产出方式**：
```bash
# docs/change-requests.md
# | CR-ID | Title | Status | Impact | Raised |
# |-------|-------|--------|--------|--------|
# | CR-001 | ... | Analyzing | Medium | 2026-10-01 |

yuleosh cr create --title "..." --priority medium
```

### BP2: Analyze and decide change requests

**CL2 要求**：分析变更请求并跟踪决策状态。

**yuleOSH 证据**：
- `docs/change-requests.md` 中包含分析记录和决策状态（Approved/Rejected/Deferred）

---

## MAN.1 — Project Management

### BP1: Define project plan

**CL2 要求**：定义包含进度的项目计划。

**yuleOSH 证据**：
- `docs/project-plan.md`（≥100 字符）

**内容要求**：
- 项目目标与范围
- 里程碑与进度计划
- 资源分配
- 风险管理策略

**产出方式**：
```bash
yuleosh project init --plan
# 或手动创建 docs/project-plan.md
```

### BP2: Monitor project progress

**CL2 要求**：对照项目计划监控进度。

**yuleOSH 证据**：
- `docs/project-plan.md` 中包含进度更新记录
- `.yuleosh/reports/pipeline-*.json` — 流水线执行记录（自动产出）

---

## MAN.2 — Requirements Management

### BP1: Manage requirements baseline

**CL2 要求**：建立需求基线并纳入配置管理。

**yuleOSH 证据**：
- `docs/requirements.md`（≥100 字符）— 需求基线文档
- `docs/system-requirements.md` — 系统需求（SYS 域）
- `docs/software-requirements.md` — 软件需求（SWE 域）

**产出方式**：
```bash
yuleosh req import --from polarion
# 或手动维护需求文档
```

### BP2: Manage requirement changes

**CL2 要求**：需求变更可追溯并版本化。

**yuleOSH 证据**：
- 需求文档中包含版本历史
- `.osh/evidence/requirements/spec-delta.md` — 需求变更记录（流水线自动产出）

---

## MAN.3 — Risk Management

### BP1: Identify risks

**CL2 要求**：识别风险并记录到风险登记册。

**yuleOSH 证据**：
- `docs/risk-register.md`（≥100 字符）

**内容要求**：
```markdown
| Risk-ID | Description | Probability | Impact | Risk Level | Owner |
|---------|-------------|-------------|--------|------------|-------|
| R-001 | ... | High | Medium | High | PM |
```

### BP2: Assess and treat risks

**CL2 要求**：评估风险并跟踪处理措施。

**yuleOSH 证据**：
- `docs/risk-register.md` 中包含处理状态（Mitigated/Accepted/Transferred/Avoided）
- 定期评审记录

---

## CL2 vs CL3 差异对照

| 维度 | CL2（已管理） | CL3（已建立） |
|------|--------------|--------------|
| 过程定义 | 项目级定义 | 组织级标准过程 |
| 证据范围 | 单项目产物 | 跨项目复用模板 |
| 度量分析 | 基本统计 | 过程性能基线 |
| 配置管理 | 基线化 | 变更控制委员会 |
| 评审深度 | 事后评审 | 同行评审 + 审计 |

---

## 快速合规检查

```bash
# 运行完整 SUP/MAN 合规检查
yuleosh compliance check --profile aspice_support_mgmt_v3.1

# 运行全 V 模型评估（SWE + SYS + SUP/MAN）
yuleosh compliance check --profile aspice_full

# 查看差距分析
yuleosh gap check --format markdown
```

---

## 证据文件最小要求

所有文档类证据需满足：
- 文件存在且非空
- 内容 ≥100 字符（排除纯标题/模板占位符）
- 使用 Markdown 或 JSON 格式
- 包含实质性内容（非模板注释）

CI 产出类证据（`.osh/ci/*.json`）由流水线自动生成，无需手动维护。

---

## 相关文档

- [Evidence Pack Structure](evidence-pack-structure.md)
- [ASPICE V-Model Support v3 Assessment](../planning/product-vmodel-support-v3-10-09.md)
- [Compliance Checker Source](../../src/yuleosh/compliance/compliance_checker.py)
