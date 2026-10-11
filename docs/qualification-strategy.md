# 合格性测试策略 (SWE.6)

## 概述

合格性测试在目标环境或等效环境（SIL/HIL 仿真）中执行，验证完整软件满足全部软件需求。

## 合格性范围

覆盖 docs/software-requirements.md 中全部功能需求与非功能需求：

| 需求 ID | 需求标题 | 验收方法 | 验收准则 |
|---------|----------|----------|----------|
| REQ-001 | Agent 驱动流水线 | E2E 测试 | spec → evidence 全流程通过 |
| REQ-002 | 需求管理 | 功能测试 | 需求 CRUD + 追溯矩阵生成 |
| REQ-003 | 代码审查 | 功能测试 | 多 Agent 审查执行并输出报告 |
| REQ-004 | CI/CD 三层流水线 | 集成测试 | L1/L25/L3 各层执行通过 |
| REQ-005 | 追溯与证据链 | 功能测试 | 双向追溯矩阵自动生成 |
| REQ-006 | 多端接入 | 功能测试 | CLI/Web/API 三端可用 |
| REQ-008 | SIL 仿真测试 | SIL 测试 | GCC 交叉编译 + QEMU 执行通过 |
| REQ-009 | FAL + HIL | HIL 测试 | Flash 写入 + 硬件在环验证 |
| REQ-010 | E2E 集成测试 | E2E 测试 | 全链路无错误 |
| REQ-NFR-001 | 性能 | 性能测试 | 100 文件项目 ≤30 秒 |
| REQ-NFR-002 | 可扩展性 | 功能测试 | 新增 yaml profile 无需改代码 |

## 测试环境

### SIL 环境 (等效环境)
- **编译器**: arm-none-eabi-gcc / riscv64-unknown-elf-gcc
- **仿真器**: QEMU (system emulation)
- **执行方式**: 交叉编译 → QEMU 运行 → 结果采集
- **证据格式**: `.osh/ci/hil-report-{commit}.json`

### HIL 环境 (目标环境)
- **硬件**: 目标 MCU 评估板
- **接口**: J-Link / ST-Link 调试器
- **执行方式**: Flash 写入 → 硬件执行 → 串口采集
- **证据格式**: `.osh/ci/hil-report-{commit}.json`

## 验收判据

- 全部合格性测试用例通过 (pass rate = 100%)
- 每条需求至少关联一个合格性测试用例
- 测试结果在目标环境或等效环境 (SIL/HIL) 中产生
- 测试证据归档至 `.osh/evidence/`

## 回归策略

- 每次代码变更后重新执行受影响的合格性测试
- 每个里程碑执行全量合格性测试
- 回归测试结果记录于 `.osh/ci/hil-report-*.json`
