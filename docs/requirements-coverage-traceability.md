# yuleOSH 需求覆盖率追踪表 (Requirements Coverage Traceability)

> **维护人**: 小马 🐴 (质量架构师)
> **版本**: v1.0.0 | **日期**: 2026-06-13
> **原则**: 需求覆盖率比行覆盖率值钱10倍 — 老陈
> **格式**: 每条 `SHALL` 条款 → 对应测试文件/测试数量/覆盖状态

---

## 追踪方法论

每一条 SHALL 需求必须映射到至少一个可执行的测试用例。测试类型缩写：
- `U` = Unit Test (pytest)
- `I` = Integration Test (CI layer 2)
- `S` = SIL Test (QEMU)
- `H` = HIL Test (hardware)
- `C` = Code Review (static check)
- `E` = E2E Test

**覆盖等级**:
- 🟢 已覆盖: ≥1 个测试通过
- 🟡 部分覆盖: 测试存在但未覆盖所有分支
- 🔴 未覆盖: 无对应测试
- ⬜ 不适用: SHOULD/MAY 或待规划

---

## 模块 1: OpenSpec 规范引擎 (`src/yuleosh/spec/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-001.1 | Agent 流水线 SDD→DDD→TDD | `test_pipeline_engine.py` | 5 | 🟢 | |
| RS-001.1 | OpenSpec 格式 (SHALL/SHOULD/MAY + GIVEN/WHEN/THEN) | `test_spec_coverage_boost.py` | 8 | 🟢 | |
| RS-001.1 | Superpowers 14 Rules 流水线阶段执行 | `test_pipeline_engine.py` | 3 | 🟢 | |
| RS-001.2 | 生成测试计划与追溯矩阵 | `test_evidence_engine.py` | 6 | 🟢 | |
| RS-001.2 | 每条 SHALL → ≥1 测试用例 | `test_evidence_engine.py` | 4 | 🟢 | |
| RS-002.1 | 需求树层级 SYS→SW→Feature→Scenario→Task | `test_evidence_engine.py` | 3 | 🟢 | |
| RS-002.1 | spec-delta 变更追踪 | `test_evidence_edge.py` | 5 | 🟢 | |
| SWR-002.1 | RFC 2119 格式支持 | `test_spec_coverage_boost.py` | 4 | 🟢 | |
| SWR-002.1 | 需求基线/版本化 (MAY) | — | 0 | ⬜ | 待实现 |
| SWR-002.2 | S.U.P.E.R 启动分析 | `test_pipeline_errors.py` | 2 | 🟡 | 仅错误路径 |
| SWR-002.2 | 需求版本间 delta 追踪 | `test_evidence_edge.py` | 3 | 🟢 | |

**模块覆盖率**: 11/12 🟢 | 1 ⬜ | 需求覆盖率: **92%**

---

## 模块 2: AI Review 引擎 (`src/yuleosh/review/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-003 | 任务级阻塞审查 | `test_review_engine.py` | 4 | 🟢 | |
| RS-003 | 双轨审查 (非阻塞AI自检 + 阻塞Agent审查) | `test_review_engine_extended.py` | 3 | 🟢 | |
| SWR-003.1 | 自动路由审查者 | `test_review_engine.py` | 3 | 🟢 | |
| SWR-003.1 | Agent 审查记录 JSON 归档 | `test_review_engine_extended.py` | 4 | 🟢 | |
| SWR-003.2 | 可配覆盖率门禁 | `test_ci_config.py` | 5 | 🟢 | |
| SWR-003.2 | 覆盖率阈值 (默认 > 98%) | `test_ci_config.py` | 3 | 🟢 | |

**模块覆盖率**: 6/6 🟢 | 需求覆盖率: **100%**

---

## 模块 3: CI/CD 三层流水线 (`src/yuleosh/ci/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-004 | 三层 CI/CD (Dev→Integration→System) | `test_ci_layers.py` | 6 | 🟢 | |
| RS-004 | ARM/RISC-V/x86_64 交叉编译 | `test_ci_engine.py` | 4 | 🟢 | |
| RS-004 | MISRA-C/C++ 静态分析门禁 | `test_c_review.py` | 8 | 🟢 | |
| RS-004 | ASPICE 合规证据包自动生成 | `test_evidence_engine.py` | 7 | 🟢 | |
| RS-004 | 固件签名/OTA (SHOULD) | — | 0 | 🔴 | 未实现 |
| RS-004 | HIL 适配器层测试 | `test_hil_runner.py` | 6 | 🟢 | |
| RS-004 | SIL 适配器层测试 | `test_sil.py` | 5 | 🟢 | |
| SWR-010.1 | CI 配置文件 `.yuleosh/ci-config.yaml` | `test_ci_config.py` | 5 | 🟢 | |
| SWR-010.1 | 层依赖链可配置 | `test_ci_layers_extended.py` | 3 | 🟢 | |
| SWR-010.2 | threshold_line/threshold_condition 可配 | `test_ci_config.py` | 4 | 🟢 | |
| SWR-010.2 | 默认覆盖率 85%/80% | `test_ci_config.py` | 2 | 🟢 | |
| SWR-010.3 | L2.5 HIL 层 (CI 2.5) | `test_ci_layer_25.py` | 8 | 🟢 | |
| SWR-010.3 | Mock 模式 (无硬件) | `test_ci_layer_25.py` | 4 | 🟢 | |

**模块覆盖率**: 11/13 🟢 | 1 🔴 1 ⬜ | 需求覆盖率: **85%**

---

## 模块 4: SIL 仿真测试 (`src/yuleosh/cross/sil_runner.py`, `src/yuleosh/sil/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-008 | ARM Cortex-M SIL | `test_sil_runner.py` | 5 | 🟢 | |
| RS-008 | QEMU 系统仿真 | `test_sil_runner.py` | 4 | 🟢 | |
| RS-008 | UART/semihosting 输出捕获 | `test_sil_runner.py` | 3 | 🟢 | |
| RS-008 | SIL → CI L2 集成 | `test_ci_layers.py` | 3 | 🟢 | |
| RS-008 | SIL 测试报告 | `test_evidence_edge.py` | 3 | 🟢 | |
| SWR-008.1 | QEMU SIL Runner 组件 | `test_sil_runner.py` | 6 | 🟢 | |
| SWR-008.1 | .elf 加载 | `test_sil_runner.py` | 3 | 🟢 | |
| SWR-008.1 | 串口输出捕获 | `test_sil_runner.py` | 4 | 🟢 | |
| SWR-008.1 | 超时终止 (30s 默认) | `test_sil_runner.py` | 3 | 🟢 | |
| SWR-008.1 | 超时可配置 | `test_sil_runner.py` | 2 | 🟢 | |
| SWR-008.1 | PASS/FAIL 基于串口断言 | `test_sil_runner.py` | 4 | 🟢 | |
| SWR-008.1 | 完整 serial log 返回 | `test_serial_monitor.py` | 5 | 🟢 | |
| SWR-008.1 | lm3s6965evb 支持 | `test_sil_runner.py` | 1 | 🟢 | |
| SWR-008.1 | stm32vldiscovery 支持 | `test_sil_runner.py` | 1 | 🟢 | |
| SWR-008.1 | RISC-V virt (SHOULD) | — | 0 | 🔴 | 待实现 |
| SWR-008.2 | HAL Mock 框架 | `test_hal_mock.c` | 6 | 🟢 | |
| SWR-008.2 | UART/GPIO/Timer/I2C/SPI mock | `test_hal_mock.c` | 5 | 🟢 | |
| SWR-008.2 | 调用序列验证 (SHOULD) | `test_hal_mock.c` | 3 | 🟢 | |
| SWR-008.3 | SIL 测试 GIVEN/WHEN/THEN 格式 | `test_sil.py` | 5 | 🟢 | |
| SWR-008.3 | CI L2 独立 SIL stage | `test_ci_layers.py` | 3 | 🟢 | |
| SWR-008.3 | 测试隔离 (独立 QEMU 进程) | `test_sil_runner.py` | 2 | 🟢 | |

**模块覆盖率**: 20/21 🟢 | 1 🔴 | 需求覆盖率: **95%**

---

## 模块 5: Flash 抽象层与 HIL 测试 (`src/yuleosh/cross/flash.py`, `src/yuleosh/hardware/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-009 | FAL 多后端 (OpenOCD/JLink/pyOCD) | `test_flash.py` | 6 | 🟢 | |
| RS-009 | 自动检测可用工具 + 回退链 | `test_flash.py` | 4 | 🟢 | |
| RS-009 | HIL 测试运行器 (flash→serial→assert) | `test_hil_runner.py` | 6 | 🟢 | |
| RS-009 | 双模式串口 (pyserial + pipe) | `test_serial_monitor.py` | 5 | 🟢 | |
| RS-009 | 测试脚本 expect/regex/assert/wait | `test_hil_runner.py` | 4 | 🟢 | |
| SWR-009.1 | FlashTool ABC + 实现 | `test_flash.py` | 5 | 🟢 | |
| SWR-009.1 | FlashRunner facade | `test_flash.py` | 4 | 🟢 | |
| SWR-009.1 | FlashResult dataclass | `test_flash.py` | 3 | 🟢 | |
| SWR-009.2 | SerialMonitor expect/read_until/assert | `test_serial_monitor.py` | 6 | 🟢 | |
| SWR-009.2 | PipeSerialMonitor | `test_serial_monitor_v060.py` | 4 | 🟢 | |
| SWR-009.3 | HilTestRunner 生命周期 | `test_hil_runner.py` | 5 | 🟢 | |
| SWR-009.3 | 测试脚本语法 | `test_hil_runner.py` | 4 | 🟢 | |

**模块覆盖率**: 12/12 🟢 | 需求覆盖率: **100%**

---

## 模块 6: SaaS/API/Dashboard (`src/yuleosh/api/`, `frontend/`)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| RS-006 | Web UI 项目管理 | `test_server_integration.py` | 5 | 🟢 | |
| RS-006 | 移动端响应 (SHOULD) | — | 0 | 🔴 | 前端响应式 |
| RS-007 | 单租户部署 | `test_auth_extended.py` | 3 | 🟢 | |
| RS-007 | 多租户隔离 (SHOULD) | `test_auth_extended.py` | 4 | 🟢 | |
| RS-007 | 组织/项目/团队层级 (SHOULD) | `test_auth_extended_handlers.py` | 4 | 🟢 | |
| UX-001.01 | 邮箱注册 | `test_jwt_auth.py` | 3 | 🟢 | |
| UX-001.02 | 邮箱登录 | `test_jwt_auth.py` | 3 | 🟢 | |
| UX-001.06 | 角色权限隔离 | `test_auth_extended.py` | 4 | 🟢 | |
| UX-001.07 | 项目数据隔离 | `test_api.py` | 4 | 🟢 | |

**模块覆盖率**: 7/9 🟢 | 2 🔴 | 需求覆盖率: **78%**

---

## 模块 7: Demo UART (新增)

| 需求 ID | SHALL 摘要 | 测试文件 | 测试数 | 覆盖状态 | 备注 |
|:--------|:-----------|:---------|:------:|:--------:|:-----|
| DEMO-UART-001.1 | `yuleosh demo uart` CLI | — | 0 | 🔴 | 待实现 |
| DEMO-UART-001.2 | 文件目录创建 | — | 0 | 🔴 | 待实现 |
| DEMO-UART-002.2 | Hello UART 输出 | — | 0 | 🔴 | 待实现 |
| DEMO-UART-003.2 | 字符回显 | — | 0 | 🔴 | 待实现 |
| DEMO-UART-005.3 | SIL Hello 断言 | — | 0 | 🔴 | 待实现 |

**模块覆盖率**: 0/5 🟢 | 5 🔴 | 需求覆盖率: **0%** (新模块)

---

## 全局汇总

| 模块 | 总 SHALL | 🟢 已覆盖 | 🟡 部分 | 🔴 未覆盖 | ⬜ MAY/SHOULD | 覆盖率 |
|:----|:--------:|:---------:|:-------:|:---------:|:-------------:|:------:|
| 1. OpenSpec 引擎 | 12 | 11 | 1 | 0 | 1 | **92%** |
| 2. AI Review 引擎 | 6 | 6 | 0 | 0 | 0 | **100%** |
| 3. CI/CD 流水线 | 13 | 11 | 0 | 1 | 1 | **85%** |
| 4. SIL 仿真测试 | 21 | 20 | 0 | 1 | 0 | **95%** |
| 5. Flash/HIL | 12 | 12 | 0 | 0 | 0 | **100%** |
| 6. SaaS/API | 9 | 7 | 0 | 2 | 0 | **78%** |
| 7. Demo UART | 5 | 0 | 0 | 5 | 0 | **0%** |
| **合计** | **78** | **67** | **1** | **9** | **2** | **86%** |

### 覆盖率缺口 TOP 5

| # | 缺失 | 模块 | 严重度 | 归因 |
|:-|:-----|:----|:------:|:-----|
| 1 | Demo UART 全部 SHALL 无测试 | 7 | 🔴 (P0) | 新模块，代码未生成 |
| 2 | 固件签名/OTA (SHOULD) | 3 | 🟡 (P2) | 功能未实现 |
| 3 | RISC-V SIL 测试 | 4 | 🟡 (P1) | QEMU RISC-V runner 未实现 |
| 4 | 移动端响应式 | 6 | 🟡 (P2) | 前端未完成 |
| 5 | S.U.P.E.R 启动分析 (部分) | 1 | 🟡 (P1) | 仅错误路径有测试 |

---

## 需求覆盖率趋势

| 版本 | 总 SHALL | 覆盖率 | 行覆盖率 (参考) |
|:----|:--------:|:------:|:--------------:|
| v0.2.0 | 25 | 72% | — |
| v0.4.0 | 48 | 81% | — |
| v0.6.0 | 62 | 84% | — |
| v1.0.0 | 78 | 86% | 86% |

> 老陈说: "需求覆盖率比行覆盖率值钱 10 倍。" 
> 目标 v1.1.0: 需求覆盖率 ≥ 95%

---

## 使用说明 (给 小克 的需求说明)

### 如何维护此追踪表

1. **新增 SHALL**: 在 spec.md 或 spec-contract.md 新增 SHALL 条款 → 在此表新增行
2. **新增测试**: 写测试后在追踪表更新 `测试文件` 和 `测试数`
3. **状态更新**: CI 流水线中的覆盖率阶段自动输出 JSON 格式追踪报告
4. **质量门禁**: 新增模块需求覆盖率必须 ≥ 80% 才能合并

### 自动化集成建议

```bash
# CI 中验证需求覆盖率
yuleosh coverage requirements --threshold 80
# 输出: ✅ SHALL: 67/78 已覆盖 (86%) — PASS (threshold: 80%)

# 查看未覆盖 SHALL
yuleosh coverage gap --module demo-uart
# 输出: 5 条未覆盖 SHALL: DEMO-UART-001.1, -001.2, -002.2, -003.2, -005.3
```
