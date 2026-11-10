# 系统需求规格 (SYS.1)

## 概述

本文件由 yuleOSH 系统需求获取步骤确定性派生，覆盖 V 模型左半顶端（系统需求分析）。

> 派生来源 (机读): `spec-derived`

## 系统需求

- **SYS-REQ-001** — 系统应提供「demo-project — Specification (BCM)」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-002** — 系统应提供「1. System Requirements」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-003** — 系统应提供「BCM-REQ-001: System Initialization」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-004** — 系统应提供「BCM-REQ-002: Diagnostic Communication」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-005** — 系统应提供「2. Door Control (门控)」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-006** — 系统应提供「BCM-DOOR-001: Door Lock Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-007** — 系统应提供「BCM-DOOR-002: Window Lift Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-008** — 系统应提供「BCM-DOOR-003: Mirror Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-009** — 系统应提供「BCM-DOOR-004: Door Status Monitoring」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-010** — 系统应提供「3. Light Control (灯光)」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-011** — 系统应提供「BCM-LIGHT-001: Headlight Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-012** — 系统应提供「BCM-LIGHT-002: Turn Signal Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-013** — 系统应提供「BCM-LIGHT-003: Interior Lighting」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-014** — 系统应提供「BCM-LIGHT-004: Brake Light」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-015** — 系统应提供「4. Wiper Control (雨刮)」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-016** — 系统应提供「BCM-WIPER-001: Wiper Speed Control」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-017** — 系统应提供「BCM-WIPER-002: Rain Sensor Integration」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-018** — 系统应提供「BCM-WIPER-003: Wash-Wipe Function」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-019** — 系统应提供「5. Power Management (电源管理)」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-020** — 系统应提供「BCM-PWR-001: Power Mode Management」能力（SHALL 满足该功能域需求）。

## 可追溯性

- 每条 SYS-REQ 的上游来源: 项目 spec —— **降级**：无涉众需求文件，SYS 需求由 spec 反推，V 模型方向（STAKE→SYS→SWE）在此倒置。
- SYS-REQ → SWE.1 映射见 `.osh/evidence/sys-to-swe-trace.json`。
