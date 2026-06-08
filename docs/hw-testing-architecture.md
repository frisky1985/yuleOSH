# v0.4.0–v0.5.0 嵌入式硬件连接测试 — 三方角色技术方案

> 基于 S.U.P.E.R 分析，由三人小队分角色产出
> 小明 🧑‍💼(PM) → 小马 🐴(质量架构) → 小克 👨‍💻(架构/实现)

---

## 一、概念澄清：SIL 与仿真分层

### SIL (Software-in-the-Loop) 定义

> SIL 是指在无真实硬件的情况下，将**生产代码**运行在模拟目标环境中进行验证。与纯单元测试的区别在于：SIL 跑的是真实编译产物（交叉编译后的二进制），而非宿主机构建。

### 硬件测试四层模型

```
Layer         Scope                    工具/技术                 硬件依赖
─────────────────────────────────────────────────────────────────────────
SIL (软件)    生产代码 + HAL 抽象层    QEMU + Renode + HAL mock   ❌ 无
PIL (处理器)  真实指令集执行           QEMU user mode + uC        ❌ 无
HIL (硬件)    真实硬件接口             OpenOCD + JLink + 夹具      ✅ 需要
CIL (集成)    多板/系统级              SSH + Docker + 测试网格     ✅ 需要
```

### yuleOSH v0.4.0 目标：SIL

SIL 层内部又分三个子层：

```
SIL Level 1: HAL Mock          — Python mock 替代外设驱动（宿主机构建, CI L1）
SIL Level 2: QEMU System       — QEMU 全系统仿真（交叉编译, CI L2）
SIL Level 3: QEMU + Peripherals— QEMU + 外设模型（UART/GPIO/Timer, CI L2）
```

---

## 二、角色讨论

### 🧑‍💼 小明 (PM / 行业专家视角)

**行业对标分析：**

| 平台 | SIL 能力 | Flash 工具 | CI 集成 | 费用 |
|:-----|:---------|:-----------|:--------|:----:|
| **Jenkins + QEMU** | QEMU 全系统 | OpenOCD, JLink | 插件化 | 免费 |
| **PlatformIO** | 无原生 SIL | PIO Unified (OpenOCD/JLink/pyOCD) | GitHub Actions | 免费 |
| **Zephyr/Twister** | QEMU + Native | 无（依赖外部） | 内置测试框架 | 免费 |
| **劳特巴赫 TRACE32** | 高级仿真 | Lauterbach Debugger | 专属插件 | 💰💰💰 |
| **Vector CANoe/VTEST** | SIL 主机级 | Vector VFlash | vTESTstudio | 💰💰💰💰💰 |
| **yuleOSH 目标 🎯** | QEMU + Renode | OpenOCD/JLink/pyOCD/ST-Link | Pipeline 原生 | 免费 |

**行业趋势分析：**

1. **CI 左移**：硬件测试正在从 HIL 向 SIL 左移。QEMU 测试能在 commit 阶段发现 70%+ 集成问题
2. **多工具链统一**：JLink 是 ARM 的事实标准（SEGGER 占 60%+ 市场），OpenOCD 是开源首选（30%），其余各占一席
3. **标准化抽象**：CMSIS-DAP/DAPLink 协议正在统一调试接口，pyOCD 是 Python 生态最佳切入点

**商业价值判断：**

| 特性 | 用户价值 | 差异化 | 实施成本 | 优先级 |
|:-----|:--------:|:------:|:--------:|:-----:|
| SIL (QEMU + Renode) | 🔥🔥🔥🔥🔥 | 🔥🔥🔥🔥 | 🟡中 | **P0** |
| 多工具Flash抽象 | 🔥🔥🔥火热 | 🔥🔥🔥🔥🔥 | 🟡中 | **P0** |
| 硬件测试报告 | 🔥🔥🔥 | 🔥🔥🔥 | 🟢低 | P1 |

---

### 🐴 小马 (质量架构师 / Spec & 可测试性)

**v0.4.0 SIL 的 Spec 定义：**

#### RS-008: 嵌入式 SIL 仿真测试
- The system SHALL support Software-in-the-Loop (SIL) testing for ARM Cortex-M targets
- The system SHALL support SIL testing via QEMU system emulation
- The system SHALL execute the cross-compiled production binary (.elf) under QEMU
- The system SHALL capture UART/semihosting output from the simulated target
- The system MAY support Renode as an alternative SIL platform

#### SWR-008.1: QEMU SIL Runner
- The system SHALL provide a `qemu-runner.py` that:
  - Loads a compiled .elf file into QEMU
  - Captures serial output (via `-serial stdio` or `-chardev`)
  - Supports timeout-based test termination
  - Reports PASS/FAIL based on serial output assertions
- The system SHALL support ARM Cortex-M3/M4 targets (e.g. `lm3s6965evb`, `stm32vldiscovery`)
- The system SHOULD support RISC-V targets (e.g. `virt` machine)

#### SWR-008.2: HAL Mock 框架
- The system SHALL provide a HAL abstraction mock layer for host-compiled tests
- The system SHALL support HAL mocking for: UART, GPIO, Timer, I2C, SPI
- The system SHOULD verify HAL call sequences against the expected state machine

#### SWR-008.3: SIL 测试规范
- The system SHALL integrate SIL tests into CI L2 (after cross-compilation, before integration)
- Each SIL test SHALL use GIVEN/WHEN/THEN format
- The system SHALL generate a SIL test report in the evidence pack
- SIL failure SHALL block the pipeline (L2 blocking)

**可测试性审查维度：**

| 审查点 | 标准 |
|:-------|:-----|
| QEMU 版本锁定 | 必须固定版本，避免跨版本行为差异 |
| 测试超时处理 | 每个 SIL 测试必须有 timeout（默认 30s） |
| 串口输出断言 | 支持 expect-like 模式（等待特定串口输出） |
| 测试隔离 | 每个测试独立 QEMU 实例，不共享状态 |
| 硬件差异抽象 | 不同 MCU 通过 YAML 配置描述，不硬编码 |

---

### 👨‍💻 小克 (架构师 / 技术方案)

**v0.4.0 SIL 架构：**

```
                              ┌──────────────────────┐
                              │   SIL Runner          │
                              │   qemu-sil-runner.py  │
                              └──────┬───────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                      │
              ▼                      ▼                      ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │ QEMU ARM Runner  │  │ QEMU RISC-V      │  │ Renode Runner    │
   │                  │  │ Runner           │  │ (可选)           │
   │ qemu-system-arm  │  │ qemu-system-riscv│  │ renode-test      │
   │ -M lm3s6965evb   │  │ -M virt          │  │                  │
   │ .elf → UART out  │  │ .elf → UART out  │  │ .elf → UART out  │
   └──────────────────┘  └──────────────────┘  └──────────────────┘
              │                      │                      │
              ▼                      ▼                      ▼
        ┌──────────────────────────────────────────────────────┐
        │               SIL 测试断言引擎                        │
        │   serial.expect("Hello World") → PASS                │
        │   serial.expect("ERROR:", timeout=5) → FAIL          │
        │   serial.read_until("Test Complete") → Assert        │
        └──────────────────────────────────────────────────────┘
```

**QEMU SIL Runner 核心实现：**

```python
# src/cross/sil_runner.py  (伪代码)
class QemuSilRunner:
    def __init__(self, config: TargetConfig):
        self.mcu = config.mcu         # "cortex-m4"
        self.machine = config.machine # "lm3s6965evb"
        self.elf = config.elf         # "build/hello-arm.elf"
        self.timeout = config.timeout # 30s
        
    def run(self, test_script: str) -> SilResult:
        """启动 QEMU, 加载 .elf, 运行测试脚本, 返回结果"""
        with QemuProcess(self.machine, self.elf) as qemu:
            serial = SerialMonitor(qemu.uart_pipe)
            result = self._execute_test(serial, test_script)
            return SilResult(
                passed=result.passed,
                log=serial.captured_log,
                coverage=self._extract_coverage(qemu)
            )
    
    def _execute_test(self, serial, script: str) -> bool:
        """支持 expect-like 断言"""
        for step in script.split("\n"):
            if step.startswith("expect:"):
                text = step.split(":", 1)[1].strip()
                assert serial.expect(text, timeout=5)
            elif step.startswith("wait:"):
                time.sleep(float(step.split(":", 1)[1]))
        return True
```

**硬件配置抽象 (YAML)：**

```yaml
# .yuleosh/targets/stm32f4.yaml
targets:
  stm32f4:
    mcu: cortex-m4
    arch: arm
    qemu:
      machine: stm32vldiscovery
      cpu: cortex-m3
      serial: "-chardev stdio,id=serial0 -serial chardev:serial0"
    flash:
      openocd:
        config: "interface/stlink-v2.cfg target/stm32f4x.cfg"
        protocol: swd
      jlink:
        device: STM32F407VG
        interface: swd
        speed: 4000
      pyocd:
        target: stm32f407vg
        frequency: 4000000

  riscv64:
    mcu: riscv64
    arch: riscv
    qemu:
      machine: virt
      cpu: rv64
      serial: "-serial stdio"
    flash:
      openocd:
        config: "interface/ftdi.cfg target/riscv.cfg"
```

---

## 三、v0.5.0 Flash 工具层扩展

### 统一的 Flash 抽象

> 不绑定单一工具，而是提供 **Flash Abstraction Layer (FAL)**

```
                          ┌──────────────────────┐
                          │   Flash Abstraction   │
                          │   Layer               │
                          │   flash.py            │
                          └──────┬───────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │                       │                       │
         ▼                       ▼                       ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ OpenOCD      │    │ JLink        │    │ pyOCD        │
  │ Runner       │    │ Runner       │    │ Runner       │
  ├──────────────┤    ├──────────────┤    ├──────────────┤
  │ 开源首选     │    │ ARM 标准     │    │ Python 原生  │
  │ 支持最广     │    │ 速度最快     │    │ CMSIS-DAP    │
  │ ST/JLINK/FTDI│    │ 专业级调试器 │    │ 零依赖安装   │
  └──────────────┘    └──────────────┘    └──────────────┘
         │
         ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │ ST-Link CLI  │    │ J-Flash CLI  │    │ DAPLink CLI  │
  │ 官方工具     │    │ SEGGER 批处理 │   │ ARM mbed     │
  └──────────────┘    └──────────────┘    └──────────────┘
```

### 各工具对比

| 特性 | **OpenOCD** | **JLink** | **pyOCD** | **ST-Link CLI** |
|:-----|:-----------|:----------|:---------|:---------------|
| 协议 | JTAG/SWD | JTAG/SWD | JTAG/SWD | SWD 仅 |
| 目标支持 | ~500+ MCU | ~2000+ MCU | CMSIS-DAP | STM32 仅 |
| 速度 | 中 | 🔥最快(50MHz) | 中 | 慢(4MHz) |
| 许可证 | GPL | 免费(有限制) | Apache 2.0 | 专有 |
| 平台 | Linux/Mac/Windows | Linux/Mac/Windows | Python 跨平台 | Linux/Mac/Windows |
| 自动检测 | ❌ 需 cfg | ✅ 自动识别 | ✅ CMSIS-DAP | ✅ 自动 |
| Python API | subprocess | pylink (3rd) | **原生** | subprocess |
| yuleOSH 优先级 | **P0 (标配)** | **P0 (专业)** | **P1 (轻量)** | P2 (ST 仅) |

### Flash Runner 实现

```python
# src/cross/flash.py (v0.5.0)
class FlashRunner:
    """Unified firmware flashing interface."""
    
    def __init__(self, target: str, tool: str = "auto"):
        self.config = self._load_target_config(target)
        self.tool = self._resolve_tool(tool)
        
    def flash(self, firmware: str) -> FlashResult:
        """Flash firmware to target. Auto-detect tool if not specified."""
        runner = self._create_runner()
        success, output = runner.write(firmware, self.config)
        return FlashResult(passed=success, log=output)
    
    def _resolve_tool(self, preferred: str) -> str:
        """Auto-detect available flash tools."""
        available = []
        if shutil.which("openocd"): available.append("openocd")
        if shutil.which("JLinkExe"): available.append("jlink")
        try:
            import pyocd; available.append("pyocd")  # noqa: F811
        except ImportError:
            pass
        if not available:
            raise FlashError("No flash tool found. Install openocd, JLink, or pyocd")
        return preferred if preferred in available else available[0]

class JLinkRunner(FlashTool):
    """SEGGER J-Link flash runner."""
    
    def __init__(self):
        self.exe = "JLinkExe"
        
    def write(self, firmware: str, config: TargetConfig) -> tuple[bool, str]:
        command = f"""
device {config.flash['jlink']['device']}
interface {config.flash['jlink']['interface']}
speed {config.flash['jlink']['speed']}
loadfile {firmware}
r
g
exit
"""
        result = subprocess.run(
            [self.exe, "-CommanderScript", "-"],
            input=command, capture_output=True, text=True, timeout=30
        )
        return ("ERROR" not in result.stdout, result.stdout)
```

---

## 四、CI 流水线集成

### v0.4.0 CI L2 升级

```
当前 L2:  clang-tidy → cross-compile → integration-tests
                                        ↓
升级 L2:  clang-tidy → cross-compile → sil-tests → integration-tests
                                        ↓
                                QEMU SIL Runner
                                + SIL 断言引擎
                                + SIL 测试报告
```

### v0.5.0 CI L2.5 新增

```
新增层:  flash → hardware-tests → collect-logs → upload-report
                ↓
        Flash Abstraction Layer
        (OpenOCD / JLink / pyOCD)
        + Serial Monitor
        + Test Assertions
```

---

## 五、产出物清单

### v0.4.0 (SIL)

| # | 产出物 | 说明 |
|:--|:-------|:-----|
| 1 | `src/cross/sil_runner.py` | QEMU SIL Runner 核心 |
| 2 | `src/cross/target_config.py` | 目标板 YAML 配置解析 |
| 3 | `src/cross/sil_assert.py` | SIL 串口断言引擎 |
| 4 | `.yuleosh/targets/*.yaml` | 目标板配置库 |
| 5 | `tests/test_sil_runner.py` | SIL Runner 单元测试 |
| 6 | CI L2 `sil-tests` stage | CI 集成 |
| 7 | `docs/spec.md` 更新 | RS-008 / SWR-008.x |
| 8 | 合规证据扩展 | SIL 测试报告纳入 evidence |

### v0.5.0 (Flash + HIL)

| # | 产出物 | 说明 |
|:--|:-------|:-----|
| 1 | `src/cross/flash.py` | Flash Abstraction Layer |
| 2 | `src/cross/flash_openocd.py` | OpenOCD Runner |
| 3 | `src/cross/flash_jlink.py` | JLink Runner |
| 4 | `src/cross/flash_pyocd.py` | pyOCD Runner (P1) |
| 5 | `src/cross/serial_monitor.py` | 串口日志采集器 |
| 6 | `src/cross/hil_runner.py` | HIL 测试框架 |
| 7 | CI L2.5 `hardware-test` stage | CI 集成 |
| 8 | 测试夹具管理 | 多板并行测试 |

---

## 六、迭代实施建议

### Sprint v0.4.0 (SIL 首发)

```
Iteration 1 (2天):  QEMU SIL Runner 核心 + ARM 目标
Iteration 2 (1天):  RISC-V 支持 + 断言引擎
Iteration 3 (1天):  CI 集成 + SIL 测试报告
Iteration 4 (1天):  HAL Mock 框架 + 合规证据扩展
```

### Sprint v0.5.0 (Flash + HIL)

```
Iteration 1 (2天):  Flash Abstraction Layer + YAML 配置
Iteration 2 (1天):  OpenOCD + JLink Runner
Iteration 3 (1天):  pyOCD + ST-Link Runner + 串口采集
Iteration 4 (1天):  HIL 测试框架 + CI 集成
```

---

## 七、预期效果

| 指标 | v0.4.0 前 | v0.4.0 后 | v0.5.0 后 |
|:-----|:---------:|:---------:|:---------:|
| 编译产物验证 | ❌ 不能 | ✅ QEMU 仿真 | ✅ QEMU |
| 硬件测试 | ❌ | ❌ | ✅ OpenOCD/JLink/pyOCD |
| 测试覆盖率 (嵌入式) | 0% | 60%+ (仿真) | 80%+ |
| CI 阻拦层级 | L1+L2 | L1+L2+SIL | L1+L2+SIL+HW |
| 合规证据完整性 | 3/5 | 4/5 | 5/5 |
