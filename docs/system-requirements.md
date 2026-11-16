# 系统需求规格 (SYS.1)

## 概述

本文件由 yuleOSH 系统需求获取步骤确定性派生，覆盖 V 模型左半顶端（系统需求分析）。

> 派生来源 (机读): `spec-derived`

## 系统需求

- **SYS-REQ-001** — 系统应提供「RS-001: LED 闪烁控制程序」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-002** — 系统应提供「SWR-001.1: 闪烁时序生成」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-003** — 系统应提供「SWR-001.2: HAL 抽象层接口」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-004** — 系统应提供「SWR-001.3: 主机验证构建」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-005** — 系统应提供「Scenario: 主机验证闪烁周期」能力（SHALL 满足该功能域需求）。
- **SYS-REQ-006** — 系统应提供「Scenario: 替换 HAL 实现移植到目标板」能力（SHALL 满足该功能域需求）。

## 可追溯性

- 每条 SYS-REQ 的上游来源: 项目 spec —— **降级**：无涉众需求文件，SYS 需求由 spec 反推，V 模型方向（STAKE→SYS→SWE）在此倒置。
- SYS-REQ → SWE.1 映射见 `.osh/evidence/sys-to-swe-trace.json`。
