# 产品确认计划 (VAL.1)

## 概述

本计划自系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，产品确认针对系统需求而非用户预期（确认方向倒置）确定性派生，共 20 条需求对应 20 个确认场景。

> 派生来源 (机读): `spec-derived`

## 确认策略

- 在目标或等效环境下执行端到端用户场景，确认产品满足预期使用。
- 确认结果须写入 `docs/validation-results.yaml`，并附可复核证据路径。
- 未提供执行记录的场景一律视为未执行，不得推断为通过。

## 确认措施与准则

| 确认场景 | 覆盖需求 | 确认环境 | 确认方法 | 通过判据 |
|:---------|:---------|:---------|:---------|:---------|
| VAL-001 | SYS-REQ-001 | 目标或等效环境 | 端到端用户场景 | 满足「demo-project — Specification (BCM)」，且无安全相关异常；判据可度量、可复核 |
| VAL-002 | SYS-REQ-002 | 目标或等效环境 | 端到端用户场景 | 满足「1. System Requirements」，且无安全相关异常；判据可度量、可复核 |
| VAL-003 | SYS-REQ-003 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-REQ-001: System Initialization」，且无安全相关异常；判据可度量、可复核 |
| VAL-004 | SYS-REQ-004 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-REQ-002: Diagnostic Communication」，且无安全相关异常；判据可度量、可复核 |
| VAL-005 | SYS-REQ-005 | 目标或等效环境 | 端到端用户场景 | 满足「2. Door Control (门控)」，且无安全相关异常；判据可度量、可复核 |
| VAL-006 | SYS-REQ-006 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-DOOR-001: Door Lock Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-007 | SYS-REQ-007 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-DOOR-002: Window Lift Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-008 | SYS-REQ-008 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-DOOR-003: Mirror Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-009 | SYS-REQ-009 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-DOOR-004: Door Status Monitoring」，且无安全相关异常；判据可度量、可复核 |
| VAL-010 | SYS-REQ-010 | 目标或等效环境 | 端到端用户场景 | 满足「3. Light Control (灯光)」，且无安全相关异常；判据可度量、可复核 |
| VAL-011 | SYS-REQ-011 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-LIGHT-001: Headlight Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-012 | SYS-REQ-012 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-LIGHT-002: Turn Signal Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-013 | SYS-REQ-013 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-LIGHT-003: Interior Lighting」，且无安全相关异常；判据可度量、可复核 |
| VAL-014 | SYS-REQ-014 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-LIGHT-004: Brake Light」，且无安全相关异常；判据可度量、可复核 |
| VAL-015 | SYS-REQ-015 | 目标或等效环境 | 端到端用户场景 | 满足「4. Wiper Control (雨刮)」，且无安全相关异常；判据可度量、可复核 |
| VAL-016 | SYS-REQ-016 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-WIPER-001: Wiper Speed Control」，且无安全相关异常；判据可度量、可复核 |
| VAL-017 | SYS-REQ-017 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-WIPER-002: Rain Sensor Integration」，且无安全相关异常；判据可度量、可复核 |
| VAL-018 | SYS-REQ-018 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-WIPER-003: Wash-Wipe Function」，且无安全相关异常；判据可度量、可复核 |
| VAL-019 | SYS-REQ-019 | 目标或等效环境 | 端到端用户场景 | 满足「5. Power Management (电源管理)」，且无安全相关异常；判据可度量、可复核 |
| VAL-020 | SYS-REQ-020 | 目标或等效环境 | 端到端用户场景 | 满足「BCM-PWR-001: Power Mode Management」，且无安全相关异常；判据可度量、可复核 |

## 确认覆盖矩阵

| 需求 | 确认场景 | 覆盖状态 |
|:-----|:---------|:---------|
| SYS-REQ-001 | VAL-001 | ✅ Planned |
| SYS-REQ-002 | VAL-002 | ✅ Planned |
| SYS-REQ-003 | VAL-003 | ✅ Planned |
| SYS-REQ-004 | VAL-004 | ✅ Planned |
| SYS-REQ-005 | VAL-005 | ✅ Planned |
| SYS-REQ-006 | VAL-006 | ✅ Planned |
| SYS-REQ-007 | VAL-007 | ✅ Planned |
| SYS-REQ-008 | VAL-008 | ✅ Planned |
| SYS-REQ-009 | VAL-009 | ✅ Planned |
| SYS-REQ-010 | VAL-010 | ✅ Planned |
| SYS-REQ-011 | VAL-011 | ✅ Planned |
| SYS-REQ-012 | VAL-012 | ✅ Planned |
| SYS-REQ-013 | VAL-013 | ✅ Planned |
| SYS-REQ-014 | VAL-014 | ✅ Planned |
| SYS-REQ-015 | VAL-015 | ✅ Planned |
| SYS-REQ-016 | VAL-016 | ✅ Planned |
| SYS-REQ-017 | VAL-017 | ✅ Planned |
| SYS-REQ-018 | VAL-018 | ✅ Planned |
| SYS-REQ-019 | VAL-019 | ✅ Planned |
| SYS-REQ-020 | VAL-020 | ✅ Planned |

## 一致性检查

- 确认准则逐条由需求派生，无孤立确认场景。
- 确认环境与方法在计划中显式声明，未声明的结果不记为 PASS。
- 系统层确认（SYS.5）与软件合格性证据（SWE.6）作为输入引用，不替代本过程的产品级确认结论。

## 可追溯性

- 确认场景覆盖 20 条需求（来源: 系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，产品确认针对系统需求而非用户预期（确认方向倒置））。
- 需求 ↔ 确认场景映射见「确认覆盖矩阵」。
- 确认结果向上追溯至涉众需求，向下关联 SYS.5 系统确认与 SWE.6 合格性证据。
