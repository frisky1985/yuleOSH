# 软件架构设计 (SWE.2)

## 架构概述

yuleOSH 采用分层架构设计，自顶向下分为 API 层、Pipeline 层、Compliance 引擎层、Evidence 层和 Report 层。各层通过明确定义的接口交互，保持单向依赖关系。

## 组件定义

### 1. API 层 (yuleosh/api/)
- **dashboard_v2.py**: V2 仪表盘 API，提供合规状态、KPI、覆盖趋势等端点
- **接口**: RESTful JSON API，输入 project_dir + profile，输出合规报告
- **依赖**: compliance/, evidence/, report/

### 2. Pipeline 层 (yuleosh/pipeline/)
- **step_handlers/**: 各过程域的步骤处理器
  - `sys_layer.py`: SYS.1~SYS.5 系统层步骤处理，生成 docs/system-*.md
  - `swe_layer.py`: SWE.1~SWE.6 软件层步骤处理
- **接口**: `handle(project_dir, context) -> StepResult`
- **依赖**: compliance/, evidence/

### 3. Compliance 引擎层 (yuleosh/compliance/)
- **compliance_checker.py**: 核心合规检查引擎，遍历项目目录比对 profile 模板
- **profile.py**: Profile 加载器，支持 yaml profile 动态加载与合并
- **profiles/**: 合规标准定义
  - `aspice_v3.1.yaml`: SWE.1~SWE.6
  - `aspice_sys_v3.1.yaml`: SYS.1~SYS.5
  - `aspice_support_mgmt_v3.1.yaml`: SUP.1/8/9/10 + MAN.1/2/3
- **接口**: `ComplianceChecker(project_dir, profile_names=[...]).run() -> dict`

### 4. Evidence 层 (yuleosh/evidence/)
- **aspice_check.py**: Gap Check 功能，`aspice_gap_check()` 面向缺口的合规报告
- **profile_a108.py**: A1-08 profile 驱动的合规检查
- **接口**: `aspice_gap_check(project_dir) -> str`

### 5. Report 层 (yuleosh/report/)
- **audit_report.py**: 审计报告生成，支持 Markdown/JSON/PDF 格式
- **接口**: `generate_audit_report(check_result, format) -> str`

## 接口规范

### 组件间接口

| 源组件 | 目标组件 | 接口 | 数据类型 |
|--------|----------|------|----------|
| API → Compliance | profile_names: list[str] | JSON | 字符串数组 |
| API → Compliance | project_dir: str | JSON | 文件路径 |
| Compliance → Profile | profile dict | Python dict | 模板定义 |
| Pipeline → Evidence | StepResult | Python dataclass | 步骤结果 |
| Evidence → Report | check_result: dict | Python dict | 检查结果 |

### 数据流

```
spec.md → Pipeline(SYS/SWE) → docs/system-*.md + docs/*.md
                                    ↓
ComplianceChecker(profiles) → check_result dict
                                    ↓
AuditReport(format) → Markdown / JSON / PDF
```

## 设计决策

- **Profile 驱动**: 合规标准通过 yaml 定义，新增标准无需修改核心代码 (REQ-NFR-002)
- **多 Profile 合并**: `_merge_profiles()` 支持多标准同时评估，顶层键互不冲突
- **反假绿**: 证据验证严格区分过程域语义，SYS/SWE 不跨域误判
