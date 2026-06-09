# Spec-Delta: v0.4.0 → v0.5.0

> 变更追踪文档 | OpenSpec 格式 | 生成: 2026-06-09

---

## 版本变更

| 属性 | v0.4.0 | v0.5.0 |
|:-----|:-------|:-------|
| pyproject.toml | 0.3.0 | 0.5.0 |
| spec.md | 0.1.1 | 0.5.0 |
| 模块 | SIL 仿真测试 | SIL + FAL + HIL |

---

## 新增需求

### RS-009: Flash 抽象层 (FAL) 与 HIL 硬件测试框架 (新)
新增 1 个系统需求、3 个软件需求。

#### SWR-009.1: Flash Abstraction Layer (FAL)
**响应:** `src/cross/flash.py` — FlashTool ABC + OpenOCDRunner + JLinkRunner + PyOCDRunner + FlashRunner

#### SWR-009.2: 串口监视器 (Serial Monitor)
**响应:** `src/cross/serial_monitor.py` — SerialMonitor (pyserial) + PipeSerialMonitor + 完整 expect/assert API

#### SWR-009.3: HIL 测试运行器
**响应:** `src/cross/hil_runner.py` — HilTestRunner + 测试脚本引擎 + 快捷方法 + hil_test()

---

## 变更需求

### RS-004: CI/CD 三层流水线
| 原 | 新 |
|:---|:---|
| `MAY support HIL/SIL adapter layer testing` | `SHALL support HIL (Hardware-in-the-Loop) adapter layer testing` + `SHALL support SIL (Software-in-the-Loop) adapter layer testing` |

**原因:** v0.5.0 实现 HIL/SIL 后，将 MAY 升级为 SHALL

---

## 新增验收场景

### Scenario: Flash 烧录 + HIL 硬件测试 (v0.5.0 新增)
覆盖 flash 自动检测、failback 链、串口断言、boot log 返回

---

## 未完成项

- [ ] CI L2.5 hardware-test stage — 架构文档已规划但未集成
- [ ] `serial_monitor.py` SerialMonitor 物理端口测试覆盖率 57% → 74%（仍需提升至 85%+）
- [ ] 并行 HIL 测试（多板支持）
- [ ] Flash 工具版本校验（参考 QEMU 版本锁定模式）

---

## 证据

- 提交: `81ccda4` + 本 spec-delta 提交
- 测试: 91 个新增测试全通过 + 708 个总测试
- 覆盖: cross/ 模块 82% (1006 stmts, 184 missed)
