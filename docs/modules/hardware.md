# `hardware` 模块设计速写

> ⚠️ **状态：未接入 Pipeline（保留为参考库）**——`src/` 生产代码无任何 `import yuleosh.hardware`，仅 tests 引用；Step 6（`hardware/integration.py:147`）当前未经运行时可达。

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/hardware/`。
> 与代码冲突时以代码为准。

## 0. 与直觉相悖处（先说结论）
- `hardware` 确为「开发板 / 烧录 / 调试探针」引擎（OpenOCD / J-Link / esptool + 串口监视 +
  GDB 回溯分析），对应 Pipeline Step 6（`hardware/integration.py:147` `step_key="hardware"`）。
- **待核实**：对 `src/` 全仓 grep `yuleosh.hardware` 结果为 **No matches**——即 `HardwareStep`
  虽定义却未被任何 `src` 生产代码 import。它可能经 step 注册表按字符串加载，或当前**未接入
  Pipeline 运行时**。建议评审时确认 Step 6 是否真正可达（见第 8 节）。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `hardware/__init__.py` | 172 |
| `hardware/debugger.py` | 449 |
| `hardware/flasher.py` | 524 |
| `hardware/integration.py` | 354 |
| `hardware/monitor.py` | 268 |

## 2. 核心职责
Pipeline Step 6：`Code → Compile → Flash → Monitor → Debug → Iterate`
（`hardware/__init__.py:5-15`）。
- 烧录：OpenOCD（`flasher.py:217`）、SEGGER J-Link（`flasher.py:299`）、esptool.py
  （ESP32/ESP8266，`flasher.py:401`），均 `subprocess` 调真实探针。
- 调试：`AIDebugger` 解析串口日志与 GDB `info registers` 回溯（`debugger.py:211, 398`），
  错误模式覆盖 HardFault / J-Link / OpenOCD / ST-Link。
- 串口监视：`SerialMonitor` 经 `pyserial` 实时捕获（`monitor.py:39, 146`）。

## 3. 关键类与函数（文件:行号）
- `HardwareDeployer`（`__init__.py:36`）：`flash` `:85`、`verify` `:93`、`monitor` `:100`、
  `analyze` `:133`、`suggest_fix` `:152`。
- `HardwareStep`（`integration.py:117`，`step_key="hardware"` `:147`）：`execute` `:157`，
  落盘 `artifacts/hardware/hardware-result.json` 与 `debug-report.json`。
- `BaseFlasher` ABC（`flasher.py:61`）+ `OpenOCDFlasher` `:198` / `JLinkFlasher` `:281` /
  `ESPToolFlasher` `:383`；异常 `FlashError`/`BinaryNotFoundError`/`ToolNotFoundError`/`HardwareNotFoundError`。
- `AIDebugger`（`debugger.py:211`）+ `DebugReport` dataclass（`:36`）。
- `SerialMonitor`（`monitor.py:39`）+ `PortNotFoundError`；`_MockSerial` 用于测试（`:242`）。

## 4. 数据模型
- `DebugReport` dataclass（`debugger.py:36`）：`error/severity/error_type/registers/stack_trace/
  raw_logs/suggestions/matched_rules`。
- `StepResult` dataclass（`integration.py:49`）：`success/flash_ok/monitor_ok/report/artifacts/
  error/duration_ms`。

## 5. 集成点
- 仅相对 import（`.flasher`/`.monitor`/`.debugger`），不依赖其它 `yuleosh.*` 子包。
- 被 import：**`src/` 中无生产调用方**（见第 0 节）；仅 tests 引用（第 7 节）。

## 6. 配置
无环境变量读取；配置来自传入 `dict`/`context`：`flasher`/`flasher_config`/`port`/`baud`/
`monitor_timeout`/`wait_for`/`max_retries`(默认 2)/`retry_delay`(默认 3)/`output_dir`
（默认 `artifacts/hardware`）。各 flasher 的 config key：OpenOCD `interface/target/...`
（`flasher.py:220-237`）；JLink `device`(默认 `STM32F407VG`)/`if`(默认 `SWD`)/`speed` `:302-307`；
esptool `chip`(默认 `esp32`)/`baud` `:404-409`。

## 7. 测试
`test_hardware.py`、`test_hardware_flasher.py`、`test_flasher_deep.py`、`test_hardware_smoke.py`、
`test_debugger_deep.py`、`test_integration_deep.py`、`test_hw_monitor_deep.py`、
`test_cross_hardware_coverage.py`。

## 8. 待决（留给评审）
- 核实 `HardwareStep` 是否已注册进 Pipeline Step 表（`src/` 无 import 可能是字符串注册或真未接入）。
  若为后者，Step 6 为「定义但未运行」的死步骤，需补注册或标注。
