# hardware API 参考

> 代码根:`src/yuleosh/hardware/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

硬件在环(HIL)引擎,定位为 Pipeline Step 6:`Code → Compile → Flash → Monitor → Debug → Iterate`。提供 AI 驱动的嵌入式硬件部署与调试管道:多协议刷写(OpenOCD / JLink / esptool)、串口实时监视与日志捕获、AI 辅助故障分析/根因定位、Pipeline 集成。`src/yuleosh/hardware/__init__.py:5-25`

核心类 `HardwareDeployer`(门面)封装 刷写 → 监视 → 分析;`HardwareStep`(`integration.py`)将其包装为 Pipeline Step。`src/yuleosh/hardware/__init__.py:36` `src/yuleosh/hardware/integration.py:117`

> ⚠️ **疑似 ORPHAN**:在 `src/yuleosh/` 范围内未找到任何 `yuleosh.hardware` 导入(见 §6)。

## 2. HTTP 端点

本子系统**不对外暴露 REST 端点**,全部为进程内 Python API。无 HTTP 层。

## 3. Python 公共 API

### 3.1 模块级函数

本子系统以类为主,无独立模块级业务函数。

### 3.2 公共类

| 类 | 关键方法(签名) | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `HardwareDeployer` | `__init__(self, flasher: str = "openocd", config: dict \| None = None, port: str \| None = None, baud: int = 115200)` | HIL 引擎门面 | `src/yuleosh/hardware/__init__.py:36,54` |
| | `flash(self, binary_path: str) -> bool` | 刷写固件 | `src/yuleosh/hardware/__init__.py:85` |
| | `verify(self, binary_path: str) -> bool` | 校验刷写内容 | `src/yuleosh/hardware/__init__.py:93` |
| | `monitor(self, port: str \| None = None, baud: int \| None = None) -> "HardwareDeployer"` | 启动串口监视(后台线程) | `src/yuleosh/hardware/__init__.py:100` |
| | `stop_monitor(self)` | 停止监视 | `src/yuleosh/hardware/__init__.py:113` |
| | `get_log(self) -> list[str]` | 取捕获的串口日志 | `src/yuleosh/hardware/__init__.py:119` |
| | `wait_for_output(self, s: str, timeout: int = 10) -> bool` | 等待特定串口字符串 | `src/yuleosh/hardware/__init__.py:125` |
| | `analyze(self, gdb_output: str \| None = None) -> DebugReport` | 分析日志,生成调试报告 | `src/yuleosh/hardware/__init__.py:133` |
| | `suggest_fix(self, error: str, code: str) -> str` | 给出修复建议 | `src/yuleosh/hardware/__init__.py:152` |
| `OpenOCDFlasher(BaseFlasher)` | `__init__(self, config: dict)`;`flash(self, binary_path)`;`verify(self, binary_path)` | OpenOCD 刷写器(STM32/ESP32 等 ARM Cortex-M) | `src/yuleosh/hardware/flasher.py:198,220` |
| `JLinkFlasher(BaseFlasher)` | `__init__(self, config: dict)`;`flash`;`verify` | SEGGER J-Link 刷写器 | `src/yuleosh/hardware/flasher.py:281,302` |
| `ESPToolFlasher(BaseFlasher)` | `__init__(self, config: dict)`;`flash(self, binary_path, port="/dev/ttyUSB0")`;`verify` | esptool.py 刷写器(ESP32/ESP8266) | `src/yuleosh/hardware/flasher.py:383,404` |
| `SerialMonitor` | `__init__(self, port: str, baud: int = 115200, timeout: float = 1.0)`;`start() -> threading.Thread`;`stop()`;`get_log() -> list[str]`;`wait_for_string(self, s, timeout=10) -> bool`;`clear_log()` | 串口监视器(后台线程,实时捕获) | `src/yuleosh/hardware/monitor.py:39,54` |
| `AIDebugger` | `__init__(self, llm_client=None)`;`analyze_log(self, log_lines: list[str]) -> DebugReport`;`suggest_fix(self, error, code) -> str`;`check_registers(self, gdb_output: str) -> dict` | AI 驱动调试分析器(规则 + 可选 LLM) | `src/yuleosh/hardware/debugger.py:211,218` |
| `HardwareStep` | `__init__(self, config: dict \| None = None)`;`execute(self, context: dict \| None = None) -> StepResult` | Pipeline Step 6 包装器 | `src/yuleosh/hardware/integration.py:117,152` |

**异常类:**

| 异常 | 用途 | 文件:行 |
| --- | --- | --- |
| `FlashError(RuntimeError)` | 刷写失败基类 | `src/yuleosh/hardware/flasher.py:41` |
| `BinaryNotFoundError(FlashError)` | 二进制不存在 | `src/yuleosh/hardware/flasher.py:45` |
| `ToolNotFoundError(FlashError)` | 工具未安装/不在 PATH | `src/yuleosh/hardware/flasher.py:49` |
| `HardwareNotFoundError(FlashError)` | 目标硬件未检测到 | `src/yuleosh/hardware/flasher.py:53` |
| `SerialMonitorError(RuntimeError)` | 串口监视错误基类 | `src/yuleosh/hardware/monitor.py:31` |
| `PortNotFoundError(SerialMonitorError)` | 串口不存在 | `src/yuleosh/hardware/monitor.py:35` |
| `HardwareStepError(RuntimeError)` | HardwareStep 执行错误 | `src/yuleosh/hardware/integration.py:113` |

### 3.3 关键数据结构

| 结构 | 说明 | 文件:行 |
| --- | --- | --- |
| `@dataclass DebugReport` | 调试报告:`error,severity,error_type,registers,stack_trace,raw_logs,suggestions,matched_rules`;含 `to_dict()` / `summary()` | `src/yuleosh/hardware/debugger.py:36`-`95` |
| `@dataclass StepResult` | 步骤结果:`success,flash_ok,monitor_ok,report,artifacts,error,duration_ms`;含 `to_dict()` / `summary()` | `src/yuleosh/hardware/integration.py:49`-`106` |
| `_ERROR_PATTERNS`(list) | 9 类错误模式规则(hardfault/assert_fail/stack_overflow/wdt_reset/div_zero/fault_isr/boot_fail/timeout/general) | `src/yuleosh/hardware/debugger.py:102`-`204` |
| `_MockSerial`(内部) | pyserial 未安装时的 fallback 串口 | `src/yuleosh/hardware/monitor.py:242` |

## 4. 配置 / 环境变量

本子系统**无专用环境变量**。运行依赖通过以下外部工具/库体现:

| 依赖 | 用途 | 文件:行 |
| --- | --- | --- |
| 外部工具 `openocd` / `JLinkExe` / `esptool.py` | 实际刷写执行(subprocess 调用) | `src/yuleosh/hardware/flasher.py:217,299,401` |
| 可选库 `serial`(pyserial) | 串口访问;缺失时 fallback `_MockSerial` | `src/yuleosh/hardware/monitor.py:155`-`167` |

> 注:无 `YULEOSH_*` 形式的环境变量;`HardwareDeployer` 配置通过构造参数 `config: dict` 传入(`__init__.py:54`)。

## 5. 调用示例

基于真实公共 API(`HardwareDeployer` / `HardwareStep`),见 `src/yuleosh/hardware/__init__.py:16-23`、`integration.py:19-28`(注意:示例按文件内 docstring 风格的 `from hardware import ...` 写法,但实际包路径为 `yuleosh.hardware`,见 §6 偏差)。

**示例 1:刷写 + 监视 + 分析**

```python
from yuleosh.hardware import HardwareDeployer      # __init__.py:27-29,36

deployer = HardwareDeployer(
    flasher="openocd",
    config={"interface": "stlink", "target": "stm32f4x"},   # __init__.py:54
    port="/dev/ttyUSB0",
)
ok = deployer.flash("build/firmware.elf")          # __init__.py:85
if ok:
    deployer.monitor(port="/dev/ttyUSB0")          # __init__.py:100
    deployer.wait_for_output("Boot OK", timeout=30) # __init__.py:125
    report = deployer.analyze()                    # __init__.py:133
    print(report.summary())
    deployer.stop_monitor()                         # __init__.py:113
```

**示例 2:作为 Pipeline 步骤**

```python
from yuleosh.hardware import HardwareStep          # integration.py:117

step = HardwareStep(config={                        # integration.py:152
    "flasher": "openocd",
    "flasher_config": {"interface": "stlink", "target": "stm32f4x"},
    "port": "/dev/ttyUSB0",
    "baud": 115200,
    "monitor_timeout": 30,
    "wait_for": "Boot OK",
})
result = step.execute({"binary_path": "build/firmware.elf"})  # integration.py:157
print(result.summary())                             # integration.py:87
```

## 6. 偏差 / 备注

- **疑似 ORPHAN(实证)**:在 `src/yuleosh/` 范围内 Grep `yuleosh.hardware`(及 `from ..hardware`、`from yuleosh.hardware import`、`import hardware` 变体)均**无命中**(`Grep src/yuleosh/` 结果:仅 `ci/stages/test.py:274` 出现 `from cross.sil_runner`,与 hardware 无关;device 包仅以注释/docstring 形式提到 `hardware.HardwareDeployer`,如 `device/__init__.py:8,18`、`device/pool.py:8`、`device/watchdog.py:7`,均非真实 import)。
  → 即:`src/yuleosh/hardware/` 在仓库内**无生产调用方**,符合"疑似 ORPHAN"盘点结论。如需最终确认,建议排查是否有持续集成/单测以外的真实消费点(目前仅 `hardware/integration.py:215` 内部 `from . import HardwareDeployer` 自引用)。

- **包导入路径异常(待核实)**:包内模块使用**顶层 `hardware.*` 绝对导入**而非相对导入,例如:
  - `src/yuleosh/hardware/flasher.py:18` `from hardware.flasher import OpenOCDFlasher`
  - `src/yuleosh/hardware/monitor.py:13` `from hardware.monitor import SerialMonitor`
  - `src/yuleosh/hardware/debugger.py:17` `from hardware.debugger import AIDebugger, DebugReport`
  同时 `__init__.py` 与 `integration.py` 的 usage docstring 写的是 `from hardware import HardwareDeployer`(`__init__.py:18`)。这暗示该包**本应作为顶层 `hardware` 包使用**,而非 `yuleosh.hardware` 子包。若以 `import yuleosh.hardware` 触发,`flasher.py:18` 的绝对 `from hardware.flasher import ...` 可能按顶层 `hardware` 解析而失败。**建议实测验证导入路径**;此偏差影响本子系统是否可被 `yuleosh.*` 正常装载。

- **`device` 层对 hardware 的引用仅为文档性**:`device` 子系统多处提到"通过 hardware.HardwareDeployer 刷写/测试",但均为注释/文档字符串,无实际 import(`device/__init__.py:8,18`、`device/pool.py:8`),故 `hardware` 并非 `device` 的运行依赖。

- **`ESPToolFlasher.flash` 签名特殊**:覆写基类签名,增加 `port` 参数(默认 `"/dev/ttyUSB0"`),基类 `BaseFlasher.flash(binary_path)` 在 `flasher.py:73`,子类在 `flasher.py:411`,调用时需注意差异。

- **`AIDebugger` 默认纯规则**:`llm_client` 为可选,缺省走规则引擎(`debugger.py:218-220`),LLM 增强需自行注入。
