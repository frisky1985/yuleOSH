# 系统验证 (SYS.3)

## 概述

本验证规划自 `docs/system-requirements.md` 的 20 条系统需求确定性派生，每条需求对应一个验证用例，验证方法由关键词启发式推断（评审/分析/测试/演示），验收准则框架待系统测试计划细化。

## 验证策略

- 验证范围覆盖全部系统需求（SYS.1），逐条可核。
- 验证方法按需求特性推断：文档类→评审，性能类→分析，交互类→演示，其余→测试。
- 验证结果关联软件层集成/合格性证据（SWE.5/SWE.6）。

## 验证用例

| 验证用例 | 覆盖需求 | 验证方法 | 验收准则框架 |
|:---------|:---------|:---------|:-------------|
| V-SYS-001 | SYS-REQ-001 | 测试 (Test) | 验证系统满足「demo-project — Specification (BCM)」需求；验收准则待系统测试计划细化 |
| V-SYS-002 | SYS-REQ-002 | 测试 (Test) | 验证系统满足「1. System Requirements」需求；验收准则待系统测试计划细化 |
| V-SYS-003 | SYS-REQ-003 | 测试 (Test) | 验证系统满足「BCM-REQ-001: System Initialization」需求；验收准则待系统测试计划细化 |
| V-SYS-004 | SYS-REQ-004 | 测试 (Test) | 验证系统满足「BCM-REQ-002: Diagnostic Communication」需求；验收准则待系统测试计划细化 |
| V-SYS-005 | SYS-REQ-005 | 测试 (Test) | 验证系统满足「2. Door Control (门控)」需求；验收准则待系统测试计划细化 |
| V-SYS-006 | SYS-REQ-006 | 测试 (Test) | 验证系统满足「BCM-DOOR-001: Door Lock Control」需求；验收准则待系统测试计划细化 |
| V-SYS-007 | SYS-REQ-007 | 测试 (Test) | 验证系统满足「BCM-DOOR-002: Window Lift Control」需求；验收准则待系统测试计划细化 |
| V-SYS-008 | SYS-REQ-008 | 测试 (Test) | 验证系统满足「BCM-DOOR-003: Mirror Control」需求；验收准则待系统测试计划细化 |
| V-SYS-009 | SYS-REQ-009 | 测试 (Test) | 验证系统满足「BCM-DOOR-004: Door Status Monitoring」需求；验收准则待系统测试计划细化 |
| V-SYS-010 | SYS-REQ-010 | 测试 (Test) | 验证系统满足「3. Light Control (灯光)」需求；验收准则待系统测试计划细化 |
| V-SYS-011 | SYS-REQ-011 | 测试 (Test) | 验证系统满足「BCM-LIGHT-001: Headlight Control」需求；验收准则待系统测试计划细化 |
| V-SYS-012 | SYS-REQ-012 | 测试 (Test) | 验证系统满足「BCM-LIGHT-002: Turn Signal Control」需求；验收准则待系统测试计划细化 |
| V-SYS-013 | SYS-REQ-013 | 测试 (Test) | 验证系统满足「BCM-LIGHT-003: Interior Lighting」需求；验收准则待系统测试计划细化 |
| V-SYS-014 | SYS-REQ-014 | 测试 (Test) | 验证系统满足「BCM-LIGHT-004: Brake Light」需求；验收准则待系统测试计划细化 |
| V-SYS-015 | SYS-REQ-015 | 测试 (Test) | 验证系统满足「4. Wiper Control (雨刮)」需求；验收准则待系统测试计划细化 |
| V-SYS-016 | SYS-REQ-016 | 测试 (Test) | 验证系统满足「BCM-WIPER-001: Wiper Speed Control」需求；验收准则待系统测试计划细化 |
| V-SYS-017 | SYS-REQ-017 | 测试 (Test) | 验证系统满足「BCM-WIPER-002: Rain Sensor Integration」需求；验收准则待系统测试计划细化 |
| V-SYS-018 | SYS-REQ-018 | 测试 (Test) | 验证系统满足「BCM-WIPER-003: Wash-Wipe Function」需求；验收准则待系统测试计划细化 |
| V-SYS-019 | SYS-REQ-019 | 测试 (Test) | 验证系统满足「5. Power Management (电源管理)」需求；验收准则待系统测试计划细化 |
| V-SYS-020 | SYS-REQ-020 | 测试 (Test) | 验证系统满足「BCM-PWR-001: Power Mode Management」需求；验收准则待系统测试计划细化 |

## 验证覆盖矩阵

| 系统需求 | 验证用例 | 覆盖状态 |
|:---------|:---------|:---------|
| SYS-REQ-001 | V-SYS-001 | ✅ Covered |
| SYS-REQ-002 | V-SYS-002 | ✅ Covered |
| SYS-REQ-003 | V-SYS-003 | ✅ Covered |
| SYS-REQ-004 | V-SYS-004 | ✅ Covered |
| SYS-REQ-005 | V-SYS-005 | ✅ Covered |
| SYS-REQ-006 | V-SYS-006 | ✅ Covered |
| SYS-REQ-007 | V-SYS-007 | ✅ Covered |
| SYS-REQ-008 | V-SYS-008 | ✅ Covered |
| SYS-REQ-009 | V-SYS-009 | ✅ Covered |
| SYS-REQ-010 | V-SYS-010 | ✅ Covered |
| SYS-REQ-011 | V-SYS-011 | ✅ Covered |
| SYS-REQ-012 | V-SYS-012 | ✅ Covered |
| SYS-REQ-013 | V-SYS-013 | ✅ Covered |
| SYS-REQ-014 | V-SYS-014 | ✅ Covered |
| SYS-REQ-015 | V-SYS-015 | ✅ Covered |
| SYS-REQ-016 | V-SYS-016 | ✅ Covered |
| SYS-REQ-017 | V-SYS-017 | ✅ Covered |
| SYS-REQ-018 | V-SYS-018 | ✅ Covered |
| SYS-REQ-019 | V-SYS-019 | ✅ Covered |
| SYS-REQ-020 | V-SYS-020 | ✅ Covered |

## 可追溯性

- 验证用例覆盖 `docs/system-requirements.md` 中的 20 条系统需求。
- 验证用例 → 系统需求（SYS.1）映射见本文「验证覆盖矩阵」章节。
- 系统级验证结果向上追溯至涉众需求，向下关联至软件层 SWE.5/SWE.6 证据。
