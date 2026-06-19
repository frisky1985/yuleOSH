# yuleOSH HIL（Hardware-in-the-Loop）集成策略

> **版本**：v1.0 | **更新**：2026-06-19
> **目标**：明确 yuleOSH 作为编排层，定义与硬件厂商的集成接口

---

## 1. 概述

### 1.1 定位

yuleOSH 的 HIL 能力定位于 **编排层（Orchestrator）**，而非替代硬件测试工具或适配器。

```
┌──────────────────────────────────────────────────┐
│                 yuleOSH HIL Layer                 │
│           (Orchestrator — 编排+报告+合规)          │
├──────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │ Flash    │  │ Serial      │  │ GDB/Debug   │  │
│  │ Adapter  │  │ Monitor     │  │ Adapter     │  │
│  └────┬─────┘  └──────┬──────┘  └──────┬──────┘  │
│       │               │                │         │
└───────┼───────────────┼────────────────┼─────────┘
        │               │                │
  ┌─────▼─────┐  ┌──────▼──────┐  ┌──────▼──────┐
  │ OpenOCD   │  │ Screen/Min  │  │ GDB /       │
  │ JLink     │  │ com         │  │ JLinkGDB    │
  │ esptool   │  │ pySerial    │  │ Server      │
  └───────────┘  └─────────────┘  └─────────────┘
```

### 1.2 核心原则

1. **编排不替代**：yuleOSH 管理流程，不重新实现刷写/调试/监控工具
2. **适配器模式**：通过插件式适配器对接不同硬件平台
3. **合规优先**：每条 HIL 测试结果自动进入 ASPICE 证据包
4. **可组合**：测试步骤可组合为复杂的测试场景（scenario）
5. **异步运行**：HIL 测试可异步执行，不影响 CI 其他环节

---

## 2. 合作伙伴接口定义

### 2.1 硬件平台适配器接口

所有硬件的集成通过 `Adapter` 抽象类实现，详见 `src/yuleosh/hardware/`。

```python
class HardwareAdapter(ABC):
    """硬件适配器基类 — 所有硬件平台必须实现此类"""

    @abstractmethod
    def flash(self, firmware_path: str, target: str) -> dict:
        """刷写固件到硬件。

        Args:
            firmware_path: 固件文件路径 (.bin / .hex / .elf)
            target: 目标设备标识

        Returns:
            dict: {"success": bool, "output": str, "duration_ms": int}
        """
        ...

    @abstractmethod
    def reset(self, target: str) -> dict:
        """复位目标设备。"""
        ...

    @abstractmethod
    def monitor(self, target: str, timeout_s: int) -> dict:
        """启动串口监视并捕获输出。

        Returns:
            dict: {"output": str, "lines": [str], "timed_out": bool}
        """
        ...

    @abstractmethod
    def debug(self, target: str, commands: list[str]) -> dict:
        """通过 GDB/JLink 执行调试命令序列。"""
        ...
```

### 2.2 内置适配器

| 适配器 | 支持平台 | 依赖工具 | 状态 |
|:-------|:---------|:---------|:-----|
| `OpenOCDAdapter` | STM32 F4/H7/G0/G4 | OpenOCD ≥ 0.12 | ✅ 已实现 |
| `JLinkAdapter` | ARM Cortex-M (全系列) | JLinkExe, JLinkGDBServer | ✅ 已实现 |
| `EsptoolAdapter` | ESP32 / ESP32-S3/S2 | esptool.py ≥ 4.0 | ✅ 已实现 |
| `SilAdapter` | Software-in-the-Loop | 本地编译 + QEMU | ✅ 已实现 |

### 2.3 第三方适配器注册

硬件厂商或合作伙伴可通过插件系统注册自定义适配器：

```python
# src/yuleosh/plugins/hil_adapters/vendor_adapter.py
from yuleosh.hardware import HardwareAdapter

class VendorMCUAdapter(HardwareAdapter):
    name = "vendor-mcu-v1"
    description = "Vendor MCU v1 HIL adapter"

    def flash(self, firmware_path: str, target: str) -> dict:
        ...

# 注册到 yuleOSH
from yuleosh.hardware import register_adapter
register_adapter(VendorMCUAdapter)
```

---

## 3. HIL 测试编排

### 3.1 测试步骤定义

HIL 测试由连续的 **断言式步骤** 构成：

```yaml
# hil-tests/uart-loopback.yaml
name: "UART Loopback Test (STM32F4)"
hardware:
  adapter: "openocd"
  target: "stm32f4discovery"
  fw_path: "build/firmware.hex"

steps:
  - name: "Flash firmware"
    action: flash
    timeout_s: 30

  - name: "Reset device"
    action: reset

  - name: "Send test data"
    action: send_serial
    data: "Hello yuleOSH HIL!\n"
    timeout_s: 5

  - name: "Verify echo"
    action: expect_serial
    expected: "yuleOSH"
    timeout_s: 10

  - name: "Measure response time"
    action: benchmark
    config:
      send: "PING\n"
      expect: "PONG"
      min_time_ms: 1
      max_time_ms: 100
```

### 3.2 测试场景（Scenario）

多个测试步骤可组合为场景：

```yaml
# hil-scenarios/full-boot-test.yaml
name: "Full Boot Sequence Test"
description: "Test complete boot sequence: flash, boot, self-test, communication"

hardware:
  # 支持多平台并行测试
  targets:
    - adapter: "openocd"
      target: "stm32f4discovery"
    - adapter: "esptool"
      target: "esp32s3"

steps:
  - scenario: flash_and_boot
    steps:
      - flash
      - reset
      - wait_s: 5
      - expect_serial: "System Ready"

  - scenario: self_test
    steps:
      - send_serial: "SELFTEST\n"
      - expect_serial: "ALL PASS"

  - scenario: communication
    steps:
      - send_serial: "ECHO hello\n"
      - expect_serial: "ECHO: hello"
```

### 3.3 编排流水线集成

HIL 测试在 CI Layer 3（系统验证）中运行：

```
Pipeline Step 8 (System Verify)
    └── HIL Test Suite
         ├── UART Loopback (STM32F4)
         ├── GPIO Test (ESP32)
         ├── Sensor Read (Custom)
         └── Evidence Collect
              ├── test_results.json
              ├── serial_logs.txt
              └── hil-test-report.md
```

---

## 4. 合规证据收集

每次 HIL 测试自动生成合规证据：

```json
{
  "test_id": "HIL-UART-001",
  "test_name": "UART Loopback STM32F4",
  "timestamp": "2026-06-19T10:30:00Z",
  "hardware": {
    "adapter": "openocd",
    "target": "stm32f4discovery",
    "firmware_hash": "sha256:abc123..."
  },
  "steps": [
    {
      "name": "Flash",
      "result": "PASS",
      "duration_ms": 8500
    },
    {
      "name": "Serial Echo",
      "result": "PASS",
      "duration_ms": 234
    }
  ],
  "overall": "PASS",
  "log_path": "reports/hil/uart-loopback-20260619.log",
  "aspice_ref": "SWE.6.BP2"
}
```

---

## 5. 异步 HIL 执行

HIL 测试通常耗时较长（刷写+启动+测试），因此支持异步模式：

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│ CI Step  │────▶│ HIL Job  │────▶│ Continue │
│ Trigger  │     │ (async)  │     │ Pipeline │
└──────────┘     └────┬─────┘     └──────────┘
                      │
               ┌──────▼──────┐
               │ Status Poll │
               │ @5s interval │
               └──────┬──────┘
                      │
               ┌──────▼──────┐
               │ HIL Result  │
               │ + Evidence  │
               └─────────────┘
```

实现方式：

```python
# 启动异步 HIL 测试
job_id = await hil_scheduler.run_async(
    test_suite="hil-tests/uart-loopback.yaml",
    target="stm32f4"
)

# 轮询状态（一般在 CI 的下一阶段）
status = await hil_scheduler.get_status(job_id)
# → {"status": "running", "progress": 0.6, "eta_seconds": 15}

# 获取结果
result = await hil_scheduler.get_results(job_id)
```

---

## 6. 支持的硬件平台

| 平台 | 适配器 | 状态 | 测试能力 |
|:-----|:-------|:-----|:---------|
| STM32F4 Discovery | OpenOCD | ✅ | UART, GPIO, I2C, SPI, ADC |
| STM32H7 Nucleo | OpenOCD | ✅ | 同上 + Ethernet, CAN, USB |
| STM32G0 | OpenOCD | ✅ | Basic GPIO, UART |
| ESP32-S3 | esptool | ✅ | WiFi, BLE, UART, I2C |
| ESP32-C3 | esptool | ✅ | WiFi, BLE, UART |
| Any ARM Cortex-M | JLink | ✅ | 完整 JTAG/SWD 调试 |

---

## 7. 错误处理策略

| 错误类型 | 处理方式 | CI 行为 |
|:---------|:---------|:--------|
| Flashing 失败 | 重试 2 次后报错 | ❌ FAIL |
| 串口超时 | 等待上限后结束步骤 | ⚠️ 记录 warning |
| 断言失败 | 记录预期 vs 实际 | ❌ FAIL |
| 设备无响应 | 硬件复位后重试 | ⚠️ 重试一次 |
| GDB 调试器断开 | 自动重连 | 🔄 自动恢复 |

---

## 8. 开发者 & 合作伙伴快速入门

### 8.1 添加新硬件平台

1. 创建适配器类继承 `HardwareAdapter`
2. 实现 `flash()`、`reset()`、`monitor()`、`debug()` 抽象方法
3. 用 `register_adapter()` 注册
4. 创建 YAML 测试用例
5. 运行 `yuleosh hil run <test-file.yaml>` 验证

### 8.2 运行现有 HIL 测试

```bash
# 列出可用 HIL 测试
yuleosh hil list

# 在指定硬件上运行测试
yuleosh hil run uart-loopback --target stm32f4discovery

# 运行完整场景
yuleosh hil scenario full-boot-test

# 查看测试结果
yuleosh hil results --last
```

### 8.3 集成 CI

```yaml
# .github/workflows/hil.yml
jobs:
  hil-test:
    runs-on: self-hosted  # 硬件需要直连 runner
    steps:
      - uses: actions/checkout@v4
      - name: Run HIL tests
        run: |
          yuleosh hil run uart-loopback --target stm32f4
          yuleosh hil run gpio-blink --target stm32f4
      - name: Collect evidence
        run: yuleosh hil evidence --output artifacts/hil-evidence.zip
      - uses: actions/upload-artifact@v4
        with:
          name: hil-evidence
          path: artifacts/hil-evidence.zip
```

---

## 9. 未来路线

| 功能 | 计划版本 | 状态 |
|:-----|:---------|:-----|
| HIL 适配器插件注册 | v1.0.0 | ✅ |
| 异步 HIL 测试编排 | v1.0.0 | ✅ |
| 多目标并行测试 | v1.1.0 | 📋 |
| HIL 测试在线 Marketplace | v1.2.0 | 📋 |
| 远程 HIL 设备池 | v1.2.0 | 📋 |
| 故障注入测试 | v1.3.0 | 📋 |
| 功耗测量集成 | v1.3.0 | 📋 |

---

*最后更新：2026-06-19*
