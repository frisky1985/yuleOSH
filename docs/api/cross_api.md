# cross API 参考

> 代码根:`src/yuleosh/cross/`;文档性质:API 接口参考(团队查阅)
> 生成:基于源码实地盘点,`文件:行` 佐证,非臆造。

## 1. 概述

yuleOSH 交叉/仿真层(cross-layer),为嵌入式目标板提供 **SIL 软件在环仿真(QEMU subprocess)**、刷写抽象层(FAL)、HIL 硬件在环测试能力。`src/yuleosh/cross/__init__.py:4-9`

**真实 SIL 实现在此包内**:`QemuSilRunner` 通过 `subprocess.Popen` 拉起 `qemu-system-arm` / `qemu-system-riscv64` 等系统模拟器,捕获串口输出并用 expect 风格脚本断言(`sil_runner.py:285`、`target_config.py:132-139`)。这与"真实 SIL 在 `cross/` 用 QEMU subprocess"的盘点一致——但应注意**生产代码引用的是顶层 `cross` 命名空间,而非 `yuleosh.cross`**(见 §6)。

三个子能力:
- **Target 配置**:`TargetConfig` dataclass + `load_target_config()` 解析 YAML 目标描述。
- **SIL**:`QemuSilRunner` / `sil_test` + `SerialAssert` 断言引擎 + `run_expect_script` 脚本解析。
- **Flash / HIL**:`FlashRunner` / `flash_firmware`(OpenOCD/JLink/pyOCD 抽象)、`HilTestRunner` / `hil_test`(Flash→Reset→Wait→Capture→Assert)、`SerialMonitor`(串口监视)。

> ⚠️ **疑似 ORPHAN**:在 `src/yuleosh/` 范围内未找到任何 `yuleosh.cross` 导入(见 §6)。

## 2. HTTP 端点

本子系统**不对外暴露 REST 端点**,全部为进程内 Python API。无 HTTP 层。

## 3. Python 公共 API

### 3.1 模块级函数

| 函数 | 签名 | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `load_target_config` | `load_target_config(name: str, base_dir: str \| None = None) -> TargetConfig` | 加载并解析目标板 YAML 配置(需 PyYAML) | `src/yuleosh/cross/target_config.py:204` |
| `discover_targets` | `discover_targets(base_dir: str \| None = None) -> dict[str, str]` | 发现可用目标 YAML(name→路径) | `src/yuleosh/cross/target_config.py:168` |
| `sil_test` | `sil_test(config: TargetConfig, *, expect_pattern=None, test_script="", timeout=None) -> SilResult` | 一次性 SIL 测试便捷函数 | `src/yuleosh/cross/sil_runner.py:423` |
| `run_expect_script` | `run_expect_script(serial: SerialAssert, script: str) -> list[str]` | 执行多行 expect 风格脚本 | `src/yuleosh/cross/sil_assert.py:331` |
| `parse_qemu_version` | `parse_qemu_version(version_output: str) -> tuple[int,int,int]` | 解析 QEMU `--version` 输出 | `src/yuleosh/cross/sil_runner.py:60` |
| `flash_firmware` | `flash_firmware(target: str \| TargetConfig, firmware: str, tool: str \| None = None) -> FlashResult` | 一次性刷写便捷函数 | `src/yuleosh/cross/flash.py:125` |
| `detect_hardware` | `detect_hardware() -> list[dict]` | 探测已连接调试探针/目标板 | `src/yuleosh/cross/flash.py:135` |
| `load_target_config_safe` | `load_target_config_safe(name: str, base_dir: str \| None = None) -> TargetConfig` | 带友好报错的配置加载 | `src/yuleosh/cross/flash.py:175` |
| `hil_test` | `hil_test(target, firmware, *, expect_pattern=None, expect_patterns=None, timeout=30.0, flash_tool=None, serial_port=None) -> HilTestResult` | 一次性 HIL 测试便捷函数 | `src/yuleosh/cross/hil_runner.py:405` |

### 3.2 公共类

| 类 | 关键方法(签名) | 用途 | 文件:行 |
| --- | --- | --- | --- |
| `TargetConfig` | `__init__(name, mcu, arch, qemu_machine, qemu_cpu, qemu_serial, qemu_extra_args=[], elf=None, default_timeout=30, flash_openocd=None, flash_jlink=None, flash_pyocd=None)`;`build_qemu_cmd() -> list[str]`;`is_arm`/`is_riscv` 属性 | 编译后的目标板配置 | `src/yuleosh/cross/target_config.py:36,94` |
| `QemuSilRunner` | `__init__(self, config: TargetConfig)`(要求 `config.elf` 已设);`run(self, test_script="", *, timeout=None, expect_pattern=None) -> SilResult` | SIL QEMU 运行器(生命周期+断言) | `src/yuleosh/cross/sil_runner.py:125,141,229` |
| `SerialAssert` | `__init__(self, log_text=None, pipe=None, timeout=10.0, max_log_size=1048576)`;`expect(self, pattern, timeout=None, *, regex=False, fail_fast=True) -> str`;`read_until(self, marker, timeout=None, *, regex=False, include_marker=False) -> str`;`@classmethod stream(pipe, timeout=10.0, max_log_size=...)`;`close()` | 串口 expect 断言引擎(支持离线/流式) | `src/yuleosh/cross/sil_assert.py:63,82,121,183,237` |
| `FlashRunner` | `__init__(self, target: str \| TargetConfig, tool: str \| None = None, base_dir: str \| None = None)`;`flash(self, firmware: str) -> FlashResult`;`erase()`;`verify()` | 统一刷写接口(自动发现可用工具) | `src/yuleosh/cross/flash.py:58,61,94` |
| `OpenOCDRunner(FlashTool)` | `write(self, firmware: str, config: TargetConfig) -> FlashResult`;`erase`;`verify`;`is_available()` | OpenOCD 刷写后端 | `src/yuleosh/cross/openocd.py:19,29` |
| `JLinkRunner(FlashTool)` | `write(self, firmware: str, config: TargetConfig) -> FlashResult`;`erase`;`is_available()` | J-Link 刷写后端 | `src/yuleosh/cross/jlink.py:20,66` |
| `PyOCDRunner(FlashTool)` | `write(self, firmware: str, config: TargetConfig) -> FlashResult`;`erase`;`is_available()` | pyOCD 刷写后端 | `src/yuleosh/cross/pyocd.py:19,33` |
| `SerialMonitor` | `__init__(self, port: str, baud=115200, timeout=5.0, encoding="utf-8")`;`open()`;`close()`;`expect(self, pattern, timeout=None, *, regex=False, fail_fast=True) -> str`;`expect_all`;`assert_text_present`;`read_until` | 物理串口监视器(pyserial) | `src/yuleosh/cross/serial_monitor.py:68,83,121,232` |
| `PipeSerialMonitor` | `__init__(self, pipe: IO[str], timeout=5.0)`;`expect(...)`;`close()` | 基于管道(如 QEMU stdout)的监视器 | `src/yuleosh/cross/serial_monitor.py:372,386` |
| `HilTestRunner` | `__init__(self, target, flash_tool=None, serial_port=None, baud=115200, flash_delay=1.0, base_dir=None)`;`run(self, firmware, *, expect_pattern=None, expect_patterns=None, test_script=None, timeout=30.0, skip_flash=False, serial_port=None) -> HilTestResult`;`flash_and_expect(...)`;`flash_and_boot(...)`;`skip_flash_test(...)` | HIL 测试运行器(Flash→Boot→Capture→Assert) | `src/yuleosh/cross/hil_runner.py:87,108,156,315` |

**异常类:**

| 异常 | 用途 | 文件:行 |
| --- | --- | --- |
| `SilAssertionError(AssertionError)` | 串口断言失败(超时/不匹配),含 `pattern/timeout/log_snippet` | `src/yuleosh/cross/sil_assert.py:44` |
| `ExpectScriptError(Exception)` | expect 脚本指令格式错误 | `src/yuleosh/cross/sil_assert.py:327` |
| `FlashError(RuntimeError)` | 无可用刷写工具/刷写失败 | `src/yuleosh/cross/base.py:38` |
| `SerialMonitorTimeout(AssertionError)` | 串口模式未在超时内匹配 | `src/yuleosh/cross/serial_monitor.py:493` |

### 3.3 关键数据结构

| 结构 | 说明 | 文件:行 |
| --- | --- | --- |
| `@dataclass TargetConfig` | 目标板配置;`build_qemu_cmd()` 生成 QEMU 命令行(`target_config.py:94`);`_qemu_binary()` 按 arch 选 `qemu-system-arm/riscv64/aarch64`(`target_config.py:132`) | `src/yuleosh/cross/target_config.py:36` |
| `@dataclass SilResult` | SIL 结果:`passed,log,coverage,elapsed,assertion_failures,error` | `src/yuleosh/cross/sil_runner.py:91` |
| `@dataclass FlashResult` | 刷写结果:`passed,log,tool,elapsed,error` | `src/yuleosh/cross/base.py:13` |
| `@dataclass HilTestResult` | HIL 结果:`passed,flash_result,boot_log,test_log,elapsed,error,phase_timings` | `src/yuleosh/cross/hil_runner.py:46` |
| `@dataclass SerialMonitorResult` | 串口会话结果:`passed,log,elapsed,assertion_failures` | `src/yuleosh/cross/serial_monitor.py:41` |
| `FlashTool(ABC)` | 抽象基类:`name`/`is_available()`/`write()`/`erase()`/`verify()` | `src/yuleosh/cross/base.py:44` |
| 常量 `MIN_QEMU_VERSION` / `MAX_QEMU_VERSION` / `RECOMMENDED_QEMU_VERSION` | QEMU 版本约束 `(8,2,0)` / `(8,3,0)` / `"8.2.x"`(`sil_runner.py:48-55`),`QemuSilRunner` 构造时校验 | `src/yuleosh/cross/sil_runner.py:48` |
| `_DEFAULT_SEARCH_DIRS`(list) | 目标 YAML 默认搜索路径 `.yuleosh/targets`、`targets`、`configs/targets` | `src/yuleosh/cross/target_config.py:161` |

## 4. 配置 / 环境变量

本子系统**无专用环境变量**(无 `YULEOSH_*` 形式)。相关外部依赖:

| 依赖 | 用途 | 文件:行 |
| --- | --- | --- |
| 外部工具 `qemu-system-arm` / `qemu-system-riscv64` / `qemu-system-aarch64` | SIL 仿真进程(`subprocess.Popen`) | `src/yuleosh/cross/target_config.py:132-139`、`sil_runner.py:285` |
| 库 `pyyaml`(可选但必需用于配置加载) | 解析目标 YAML;缺失时 `load_target_config` 抛 `RuntimeError` | `src/yuleosh/cross/target_config.py:25-28,226` |
| 外部工具 `openocd` / `JLinkExe` / `pyocd`(可选,按目标) | FAL 刷写后端;自动 `is_available()` 探测 | `src/yuleosh/cross/openocd.py:217`、`jlink.py:299`、`pyocd.py` |
| 库 `serial`(pyserial,可选) | `SerialMonitor` 物理串口;缺失时 `open()` 抛 `RuntimeError` | `src/yuleosh/cross/serial_monitor.py:145-156` |

> 注:目标配置通过构造参数 `TargetConfig` 或 YAML 文件(经 `load_target_config(name)`)传入;无 env var 注入路径。

## 5. 调用示例

基于真实公共 API(`load_target_config` / `QemuSilRunner` / `sil_test` / `hil_test`),见 `src/yuleosh/cross/sil_runner.py:11-22`、`target_config.py:12-14`、`hil_runner.py:17-23`。

**示例 1:SIL(QEMU)测试**

```python
from yuleosh.cross import load_target_config, sil_test      # __init__.py:11,13

cfg = load_target_config("stm32f4")                         # target_config.py:204
cfg.elf = "build/hello-arm.elf"                            # 必须设置 elf

result = sil_test(cfg, expect_pattern="Hello World")        # sil_runner.py:423
assert result.passed                                       # sil_runner.py:92
print(result.log[:500])                                    # 捕获的串口输出
```

**示例 2:HIL 测试(Flash → 等待模式串)**

```python
from yuleosh.cross import hil_test                         # __init__.py:32

result = hil_test(                                         # hil_runner.py:405
    target="stm32f4",
    firmware="build/firmware.elf",
    expect_pattern="Test PASSED",
    timeout=30,
)
assert result.passed
print(result.boot_log)
```

## 6. 偏差 / 备注

- **疑似 ORPHAN(实证)**:在 `src/yuleosh/` 范围内 Grep `yuleosh.cross`(及 `from ..cross`、`from yuleosh.cross import`、`import cross` 变体)**均无命中**。即:作为 `yuleosh.cross` 子包,本目录**无生产调用方**。

- **生产 SIL 引用的是顶层 `cross`,而非 `yuleosh.cross`(关键)**:唯一对 SIL 的真实引用出现在 `src/yuleosh/ci/stages/test.py:274-275`:
  ```python
  from cross.sil_runner import SilResult, sil_test
  from cross.target_config import TargetConfig
  ```
  这是一个**顶层 `cross` 命名空间**(bare `cross`),与 `yuleosh.cross` 是**不同的导入路径**。本盘点确认:当前仓库**不存在顶层 `cross/` 目录**(`Glob cross/**` 无结果;`ls` 确认 `NO top-level cross dir`)。因此:
  - 该 `ci/stages/test.py` 的 `from cross...` 在当前 checkout 中**无法解析**(除非运行期另有路径注入或该包来自外部依赖);
  - `src/yuleosh/cross/` 这一套完整的 QEMU SIL / FAL / HIL 实现,**与**生产引用的 `cross` 命名空间脱节,处于 ORPHAN 状态。
  → 与盘点"cross 非交叉编译管理,真实 SIL 在 cross/ 用 QEMU subprocess"相呼应,但需提醒:**若要让本目录被真正使用,需澄清 `yuleosh.cross` 与 `cross` 是否为同一代码的两份拷贝,或重新接线导入路径**。

- **包内部存在顶层绝对导入(待核实)**:`src/yuleosh/cross/sil_assert.py:14` 写 `from sil_assert import SerialAssert`(对自身模块的顶层绝对导入),`sil_runner.py` 等用相对导入(`from .sil_assert import ...`,`sil_runner.py:38`)。若以 `yuleosh.cross` 形式导入,`sil_assert.py:14` 的 `from sil_assert import ...` 可能按顶层 `sil_assert` 解析而失败。**建议实测验证导入路径**。

- **`sil_runner.py` 与 `sil_assert.py` 的 logger 名为 `sil.runner` / `sil.assert`(`sil_runner.py:41`、`sil_assert.py:36`),而非 `yuleosh.cross.*`**;模块 docstring 亦标注 `from sil_assert import SerialAssert`(`sil_assert.py:14`),进一步印证该包最初以顶层 `sil_*` / `cross` 命名空间设计。

- **QEMU 版本强约束**:`QemuSilRunner.__init__` 强制要求 QEMU 版本 ∈ [8.2.0, 8.3.0)(`sil_runner.py:48-55, 209-223`),低于下限直接 `RuntimeError`。这是 `cross` 区别于一般 QEMU 封装的强约束点。

- **`FlashResult`/`FlashTool`/`FlashError` 定义在 `base.py`**:`flash.py` 仅为 re-export(`flash.py:19` `from .base import ...`),`base.py` 是真正的类型归属地(`base.py:13-78`)。

- **`detect_hardware` 仅探测 pyocd / JLink**:见 `flash.py:135-172`;OpenOCD 未纳入探测列表。

- **`SerialMonitor` 与 `SerialAssert` 两套串口断言 API 并存**:`cross/serial_monitor.py` 的 `SerialMonitor.expect`(基于 pyserial,`serial_monitor.py:232`)与 `cross/sil_assert.py` 的 `SerialAssert.expect`(基于管道/离线文本,`sil_assert.py:121`)接口相似但实现独立,`HilTestRunner` 用前者、`QemuSilRunner` 用后者,注意区分。
