# `cross` 模块设计速写

> 本篇为「模块设计速写」（speed-write），基于 2026-10-07 实读 `src/yuleosh/cross/`。
> 与代码冲突时以代码为准。

## 0. 与直觉相悖处（先说结论）
- **`cross` 不是交叉编译 / 工具链（`arm-none-eabi-gcc`）管理模块**。其 docstring 自述为
  「SIL 仿真、flash 抽象、HIL 测试能力」（`__init__.py:4-9`）。全盘 grep `arm-none-eabi|gcc|
  toolchain` 仅命中 `re.compile` 与 `hello.c` 注释。**实际职责**：Flash 抽象层 + QEMU SIL
  运行器 + 串口断言 + HIL 编排。唯一「编译」相关物是 `cross/hello.c`（待交叉编译的被测 ELF
  样例）与 `cross/hal_mock/`（用宿主 `gcc` 编译的 HAL 桩，供原生单测）。
- **待核实**：对 `src/` 全仓 grep `yuleosh.cross` 结果为 **No matches**——即 `cross` 是
  **未被生产代码引用的孤岛库**（仅 tests 引用）。若设计文档称其「接入 Pipeline 仿真/测试」，
  需核实是否经 step 注册表加载。

## 1. 文件清单
| 文件 | 行数 |
|---|---|
| `cross/__init__.py` | 67 |
| `cross/base.py` | 78 |
| `cross/target_config.py` | 372 |
| `cross/flash.py` | 186 |
| `cross/jlink.py` | 142 |
| `cross/openocd.py` | 170 |
| `cross/pyocd.py` | 106 |
| `cross/serial_monitor.py` | 495 |
| `cross/sil_assert.py` | 407 |
| `cross/sil_runner.py` | 446 |
| `cross/hil_runner.py` | 436 |
| `cross/hello.c` + `cross/hal_mock/*` | （C 测试桩，非 Python） |

## 2. 核心职责
- **Flash 抽象**：`FlashTool` ABC（`base.py:44`）+ `OpenOCDRunner`/`JLinkRunner`/`PyOCDRunner`
  三类后端（`flash.py` 编排）。
- **QEMU SIL 运行器**：`QemuSilRunner` 调 `qemu-system-arm` 等（`sil_runner.py:125`），含版本
  检查（`MIN/MAX/RECOMMENDED_QEMU_VERSION` `:48-54`）与覆盖率抽取（`_extract_coverage` `:409`）。
- **串口监视 / 断言**：`SerialMonitor`（`serial_monitor.py:68`，`expect`/`expect_all`/
  `assert_text_present`）、`SerialAssert`（`sil_assert.py:63`）、`run_expect_script` `:331`。
- **HIL 编排**：`HilTestRunner`（`hil_runner.py:87`，`flash_and_expect`/`flash_and_boot`）。
- 无 async / 无 HTTP / 无 CLI。

## 3. 关键类与函数（文件:行号）
- `TargetConfig` dataclass（`target_config.py:36`）：`name/mcu/arch/qemu_machine/qemu_cpu/
  qemu_serial/qemu_extra_args/elf/default_timeout/flash_*`；`discover_targets` `:168`、
  `load_target_config` `:204`。YAML 搜索目录 `.yuleosh/targets`/`targets`/`configs/targets`
  （`:161-165`）。
- `FlashResult` dataclass（`base.py:13`）、`FlashTool` ABC（`base.py:44`）、`FlashRunner`
  （`flash.py:58`，`flash`/`erase`/`verify`）。
- `QemuSilRunner`（`sil_runner.py:125`）、`SilResult` dataclass（`:91`）、便捷 `sil_test` `:423`。
- `SerialMonitor`（`serial_monitor.py:68`）、`SerialMonitorResult`（`:41`）、`PipeSerialMonitor`
  （`:372`）、`SerialMonitorTimeout`（`:493`）。
- `SerialAssert`（`sil_assert.py:63`）、`SilAssertionError`（`:44`）、`run_expect_script` `:331`。
- `HilTestRunner`（`hil_runner.py:87`）、`HilTestResult` dataclass（`:46`）、`hil_test` `:405`。

## 4. 数据模型
全部 dataclass（无 pydantic）：`TargetConfig`、`FlashResult`、`SerialMonitorResult`、
`SilResult`（`passed/log/coverage/elapsed/assertion_failures/error`）、`HilTestResult`
（`flash_result/boot_log/test_log/elapsed/error/phase_timings`）。

## 5. 集成点
- 仅相对 import（`.base`/`.target_config`/`.sil_assert`/...），**不 import 任何 `yuleosh.*`
  其它子包**。
- 被 import：**`src/` 中无生产调用方**（见第 0 节）；仅 tests 引用（第 7 节）。

## 6. 配置
无环境变量读取；配置来自传入 `dict` / `TargetConfig` YAML。外部 CLI（`subprocess`）：`openocd` /
`JLinkExe` / `pyocd` / `qemu-system-*`。

## 7. 测试
`test_cross_hardware_coverage.py`、`test_sil_runner_deep_v2.py`、`test_sil_runner.py`、
`test_flash.py`、`test_cross_flash_deep.py`、`test_serial_monitor.py`、`test_serial_monitor_v060.py`、
`test_cross_monitor_deep.py`、`test_cross_sil_assert_deep.py`、`test_target_config_deep.py`、
`test_target_config_smoke.py`、`test_hil_runner.py`、`test_hil_runner_deep_v2.py`、
`test_cross_smoke.py`、`test_max_import.py`。

## 8. 待决（留给评审）
- 核实 `cross` 是否经 step 注册表接入 Pipeline 仿真/测试（当前 `src` 无 import）。
- 模块名 `cross` 易误导为「交叉编译」；建议在文档/命名上澄清为「cross-compiled target 测试
  编排」（Flash/SIL/HIL），避免与 `arm-none-eabi-gcc` 工具链混淆。
