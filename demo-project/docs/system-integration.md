# 系统集成 (SYS.4)

## 概述

本集成规划自 `docs/system-architecture.md` 的 20 个系统元素确定性派生，按元素顺序生成集成步骤，每步标注集成对象与接口验证点。

## 集成策略

- 集成顺序按系统元素依赖关系自底向上，先集成无依赖元素。
- 桩/驱动按接口规范构造。
- 集成序列在 `.osh/ci/` 中复现（软件层集成测试 SWE.5 提供执行记录）。

## 集成序列

| 集成步骤 | 系统元素 | 覆盖需求 | 集成内容与验证点 |
|:---------|:---------|:---------|:----------------|
| INT-001 | SE-01 | SYS-REQ-001 | 集成 SE-01（承载「demo-project — Specification (BCM)」能力…）；验证接口数据流正确性 |
| INT-002 | SE-02 | SYS-REQ-002 | 集成 SE-02（承载「1. System Requirements」能力；对外仅通过已定义接口交…）；验证接口数据流正确性 |
| INT-003 | SE-03 | SYS-REQ-003 | 集成 SE-03（承载「BCM-REQ-001: System Initialization」能力…）；验证接口数据流正确性 |
| INT-004 | SE-04 | SYS-REQ-004 | 集成 SE-04（承载「BCM-REQ-002: Diagnostic Communication…）；验证接口数据流正确性 |
| INT-005 | SE-05 | SYS-REQ-005 | 集成 SE-05（承载「2. Door Control (门控)」能力；对外仅通过已定义接口交互，…）；验证接口数据流正确性 |
| INT-006 | SE-06 | SYS-REQ-006 | 集成 SE-06（承载「BCM-DOOR-001: Door Lock Control」能力；对外…）；验证接口数据流正确性 |
| INT-007 | SE-07 | SYS-REQ-007 | 集成 SE-07（承载「BCM-DOOR-002: Window Lift Control」能力；…）；验证接口数据流正确性 |
| INT-008 | SE-08 | SYS-REQ-008 | 集成 SE-08（承载「BCM-DOOR-003: Mirror Control」能力；对外仅通过…）；验证接口数据流正确性 |
| INT-009 | SE-09 | SYS-REQ-009 | 集成 SE-09（承载「BCM-DOOR-004: Door Status Monitoring」…）；验证接口数据流正确性 |
| INT-010 | SE-10 | SYS-REQ-010 | 集成 SE-10（承载「3. Light Control (灯光)」能力；对外仅通过已定义接口交互…）；验证接口数据流正确性 |
| INT-011 | SE-11 | SYS-REQ-011 | 集成 SE-11（承载「BCM-LIGHT-001: Headlight Control」能力；对…）；验证接口数据流正确性 |
| INT-012 | SE-12 | SYS-REQ-012 | 集成 SE-12（承载「BCM-LIGHT-002: Turn Signal Control」能力…）；验证接口数据流正确性 |
| INT-013 | SE-13 | SYS-REQ-013 | 集成 SE-13（承载「BCM-LIGHT-003: Interior Lighting」能力；对…）；验证接口数据流正确性 |
| INT-014 | SE-14 | SYS-REQ-014 | 集成 SE-14（承载「BCM-LIGHT-004: Brake Light」能力；对外仅通过已定…）；验证接口数据流正确性 |
| INT-015 | SE-15 | SYS-REQ-015 | 集成 SE-15（承载「4. Wiper Control (雨刮)」能力；对外仅通过已定义接口交互…）；验证接口数据流正确性 |
| INT-016 | SE-16 | SYS-REQ-016 | 集成 SE-16（承载「BCM-WIPER-001: Wiper Speed Control」能力…）；验证接口数据流正确性 |
| INT-017 | SE-17 | SYS-REQ-017 | 集成 SE-17（承载「BCM-WIPER-002: Rain Sensor Integratio…）；验证接口数据流正确性 |
| INT-018 | SE-18 | SYS-REQ-018 | 集成 SE-18（承载「BCM-WIPER-003: Wash-Wipe Function」能力；…）；验证接口数据流正确性 |
| INT-019 | SE-19 | SYS-REQ-019 | 集成 SE-19（承载「5. Power Management (电源管理)」能力；对外仅通过已定…）；验证接口数据流正确性 |
| INT-020 | SE-20 | SYS-REQ-020 | 集成 SE-20（承载「BCM-PWR-001: Power Mode Management」能力…）；验证接口数据流正确性 |

## 集成覆盖矩阵

| 系统元素 | 集成步骤 | 覆盖状态 |
|:---------|:---------|:---------|
| SE-01 | INT-001 | ✅ Covered |
| SE-02 | INT-002 | ✅ Covered |
| SE-03 | INT-003 | ✅ Covered |
| SE-04 | INT-004 | ✅ Covered |
| SE-05 | INT-005 | ✅ Covered |
| SE-06 | INT-006 | ✅ Covered |
| SE-07 | INT-007 | ✅ Covered |
| SE-08 | INT-008 | ✅ Covered |
| SE-09 | INT-009 | ✅ Covered |
| SE-10 | INT-010 | ✅ Covered |
| SE-11 | INT-011 | ✅ Covered |
| SE-12 | INT-012 | ✅ Covered |
| SE-13 | INT-013 | ✅ Covered |
| SE-14 | INT-014 | ✅ Covered |
| SE-15 | INT-015 | ✅ Covered |
| SE-16 | INT-016 | ✅ Covered |
| SE-17 | INT-017 | ✅ Covered |
| SE-18 | INT-018 | ✅ Covered |
| SE-19 | INT-019 | ✅ Covered |
| SE-20 | INT-020 | ✅ Covered |

## 可追溯性

- 集成步骤覆盖 `docs/system-architecture.md` 中的 20 个系统元素。
- 集成项 → 系统架构元素（SYS.2）映射见本文「集成覆盖矩阵」章节。
- 系统集成结果向上追溯至系统需求（SYS.1），向下关联软件组件（SWE.3）。
