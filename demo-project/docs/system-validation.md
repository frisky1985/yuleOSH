# 系统确认 (SYS.5)

## 概述

本确认规划自系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，确认针对系统需求而非涉众需求（V 模型方向倒置）确定性派生，共 20 条需求对应 20 个确认场景。

> 派生来源 (机读): `spec-derived`

## 确认策略

- 在目标或等效环境下运行用户场景，确认满足涉众需求。
- 确认场景复用软件合格性测试（SWE.6）的仿真/HIL 证据。
- 每条涉众需求具备可执行验收准则与通过判据。

## 确认场景

| 确认场景 | 覆盖需求 | 确认内容与验收准则框架 |
|:---------|:---------|:----------------------|
| VAL-001 | SYS-REQ-001 | 在目标/等效环境下运行用户场景，确认满足「demo-project — Specification (BCM)」；验收准则待确认计划细化 |
| VAL-002 | SYS-REQ-002 | 在目标/等效环境下运行用户场景，确认满足「1. System Requirements」；验收准则待确认计划细化 |
| VAL-003 | SYS-REQ-003 | 在目标/等效环境下运行用户场景，确认满足「BCM-REQ-001: System Initialization」；验收准则待确认计划细化 |
| VAL-004 | SYS-REQ-004 | 在目标/等效环境下运行用户场景，确认满足「BCM-REQ-002: Diagnostic Communication」；验收准则待确认计划细化 |
| VAL-005 | SYS-REQ-005 | 在目标/等效环境下运行用户场景，确认满足「2. Door Control (门控)」；验收准则待确认计划细化 |
| VAL-006 | SYS-REQ-006 | 在目标/等效环境下运行用户场景，确认满足「BCM-DOOR-001: Door Lock Control」；验收准则待确认计划细化 |
| VAL-007 | SYS-REQ-007 | 在目标/等效环境下运行用户场景，确认满足「BCM-DOOR-002: Window Lift Control」；验收准则待确认计划细化 |
| VAL-008 | SYS-REQ-008 | 在目标/等效环境下运行用户场景，确认满足「BCM-DOOR-003: Mirror Control」；验收准则待确认计划细化 |
| VAL-009 | SYS-REQ-009 | 在目标/等效环境下运行用户场景，确认满足「BCM-DOOR-004: Door Status Monitoring」；验收准则待确认计划细化 |
| VAL-010 | SYS-REQ-010 | 在目标/等效环境下运行用户场景，确认满足「3. Light Control (灯光)」；验收准则待确认计划细化 |
| VAL-011 | SYS-REQ-011 | 在目标/等效环境下运行用户场景，确认满足「BCM-LIGHT-001: Headlight Control」；验收准则待确认计划细化 |
| VAL-012 | SYS-REQ-012 | 在目标/等效环境下运行用户场景，确认满足「BCM-LIGHT-002: Turn Signal Control」；验收准则待确认计划细化 |
| VAL-013 | SYS-REQ-013 | 在目标/等效环境下运行用户场景，确认满足「BCM-LIGHT-003: Interior Lighting」；验收准则待确认计划细化 |
| VAL-014 | SYS-REQ-014 | 在目标/等效环境下运行用户场景，确认满足「BCM-LIGHT-004: Brake Light」；验收准则待确认计划细化 |
| VAL-015 | SYS-REQ-015 | 在目标/等效环境下运行用户场景，确认满足「4. Wiper Control (雨刮)」；验收准则待确认计划细化 |
| VAL-016 | SYS-REQ-016 | 在目标/等效环境下运行用户场景，确认满足「BCM-WIPER-001: Wiper Speed Control」；验收准则待确认计划细化 |
| VAL-017 | SYS-REQ-017 | 在目标/等效环境下运行用户场景，确认满足「BCM-WIPER-002: Rain Sensor Integration」；验收准则待确认计划细化 |
| VAL-018 | SYS-REQ-018 | 在目标/等效环境下运行用户场景，确认满足「BCM-WIPER-003: Wash-Wipe Function」；验收准则待确认计划细化 |
| VAL-019 | SYS-REQ-019 | 在目标/等效环境下运行用户场景，确认满足「5. Power Management (电源管理)」；验收准则待确认计划细化 |
| VAL-020 | SYS-REQ-020 | 在目标/等效环境下运行用户场景，确认满足「BCM-PWR-001: Power Mode Management」；验收准则待确认计划细化 |

## 确认覆盖矩阵

| 需求 | 确认场景 | 覆盖状态 |
|:-----|:---------|:---------|
| SYS-REQ-001 | VAL-001 | ✅ Covered |
| SYS-REQ-002 | VAL-002 | ✅ Covered |
| SYS-REQ-003 | VAL-003 | ✅ Covered |
| SYS-REQ-004 | VAL-004 | ✅ Covered |
| SYS-REQ-005 | VAL-005 | ✅ Covered |
| SYS-REQ-006 | VAL-006 | ✅ Covered |
| SYS-REQ-007 | VAL-007 | ✅ Covered |
| SYS-REQ-008 | VAL-008 | ✅ Covered |
| SYS-REQ-009 | VAL-009 | ✅ Covered |
| SYS-REQ-010 | VAL-010 | ✅ Covered |
| SYS-REQ-011 | VAL-011 | ✅ Covered |
| SYS-REQ-012 | VAL-012 | ✅ Covered |
| SYS-REQ-013 | VAL-013 | ✅ Covered |
| SYS-REQ-014 | VAL-014 | ✅ Covered |
| SYS-REQ-015 | VAL-015 | ✅ Covered |
| SYS-REQ-016 | VAL-016 | ✅ Covered |
| SYS-REQ-017 | VAL-017 | ✅ Covered |
| SYS-REQ-018 | VAL-018 | ✅ Covered |
| SYS-REQ-019 | VAL-019 | ✅ Covered |
| SYS-REQ-020 | VAL-020 | ✅ Covered |

## 可追溯性

- 确认场景覆盖 20 条需求（来源: 系统需求（SYS-REQ-xxx）—— **降级**：无涉众需求文件，确认针对系统需求而非涉众需求（V 模型方向倒置））。
- 确认场景 → 需求映射见本文「确认覆盖矩阵」章节。
- 系统确认结果向上追溯至涉众需求，向下关联系统需求（SYS.1）与软件合格性证据。
