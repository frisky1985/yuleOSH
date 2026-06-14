# yuleOSH Demo UART — Spec 契约层

> **版本**: 1.0.0 | **状态**: 已批准 | **格式**: DEMO-UART-XXX
> **上游**: 小明 (需求) · **审批**: 小马 🐴 (质量架构师)
> **日期**: 2026-06-13

---

## 1. 概述

Demo UART 是 yuleOSH 的快速演示项目，用于向新用户展示"从 spec 到真实硬件输出"的全流程。用户仅需 2 步 CLI 命令即可在 QEMU 仿真或真实 MCU 上看到 UART 串口输出，零配置零门槛。

**演示目标**: 用户可在 2 分钟内完成 `yuleosh demo uart` → 看到串口输出 "Hello from yuleOSH Demo UART"。

---

## 2. 需求定义

### DEMO-UART-001: 演示初始化

- The system SHALL provide a `yuleosh demo uart` CLI subcommand that initializes a demo UART project in the current directory.
- The system SHALL create the following files on initialization:
  - `main/main.c` — 主源文件，包含 UART 初始化与消息循环
  - `CMakeLists.txt` — 顶层 CMake 构建配置
  - `main/CMakeLists.txt` — 组件 CMake 配置
  - `README.md` — 项目说明
- The demo project SHALL use ESP-IDF as the build framework (ESP32 target by default).
- The system MAY support additional MCU targets (STM32, ARM Cortex-M) via `--target` flag.

#### Reason
演示项目必须一令创建、零配置运行。默认 ESP32 目标确保最广泛的开发者可以零硬件成本在 QEMU 中验证。

#### GIVEN a new user in an empty directory
##### WHEN the user runs `yuleosh demo uart`
##### THEN a `uart-demo/` directory SHALL be created
##### AND `uart-demo/CMakeLists.txt` SHALL exist and be syntactically valid
##### AND `uart-demo/main/main.c` SHALL exist and contain a `app_main()` function

---

### DEMO-UART-002: UART 串口发送

- The system SHALL configure UART at 115200 baud (8N1) by default.
- The system SHALL output the string `"Hello from yuleOSH Demo UART\n"` on system boot.
- The system SHALL output a periodic heartbeat message `"[yuleOSH] alive — {uptime}s\n"` every 5 seconds.
- The system SHALL output `"Demo UART ready — send characters to echo\n"` after initialization.
- The system MAY support configurable baud rate via `sdkconfig` or compile-time `#define`.

#### Reason
UART 串口发送是演示的核心功能——用户通过串口监视器看到实时输出即证明 pipeline 全链路正常运行。

#### GIVEN the demo firmware is flashed and running
##### WHEN the target boots
##### THEN the serial output SHALL contain `"Hello from yuleOSH Demo UART"`
##### AND the serial output SHALL contain `"Demo UART ready — send characters to echo"`

#### GIVEN the demo firmware has been running for 12 seconds
##### WHEN the serial monitor captures output
##### THEN the output SHALL contain at least two heartbeat lines matching `[yuleOSH] alive — \d+s`

---

### DEMO-UART-003: UART 串口接收与回显 (Echo)

- The system SHALL configure UART RX to receive characters.
- The system SHALL echo back every received character with prefix `"Echo: {char}\n"`.
- The system SHALL echo back received strings terminated by `\r` or `\n` with prefix `"Line: {string}\n"`.
- The system SHALL handle at least 64-byte RX buffer without data loss.
- The system MAY support configurable RX buffer size.

#### Reason
回显功能验证 UART 双向通信（TX+RX），覆盖完整的 HAL UART 接口测试。这是向用户展示"传感→处理→输出"闭环的最佳演示场景。

#### GIVEN the demo firmware is ready
##### WHEN the user sends the character `'A'` over serial
##### THEN the system SHALL respond with `"Echo: A\n"`

#### GIVEN the demo firmware is ready
##### WHEN the user sends the string `"hello"` followed by `\n` over serial
##### THEN the system SHALL respond with `"Line: hello\n"`

---

### DEMO-UART-004: 演示清理

- The system SHALL provide a `yuleosh demo uart --clean` flag that removes the generated demo project.
- The system SHALL confirm before removing with `"Remove uart-demo/? [y/N]"`.

#### Reason
演示不应在用户系统上留下残留文件。清理子命令确保演示可以反复重置。

#### GIVEN a demo project exists at `uart-demo/`
##### WHEN the user runs `yuleosh demo uart --clean`
##### THEN the system SHALL prompt for confirmation
##### AND if confirmed, the `uart-demo/` directory SHALL be removed

---

### DEMO-UART-005: SIL 测试兼容

- The system SHALL produce a firmware binary compatible with QEMU ESP32 system emulation.
- The system SHALL support verification via `yuleosh ci run 2` (CI Layer 2 cross-compilation + SIL).
- The system SHALL pass a SIL test that asserts `"Hello from yuleOSH Demo UART"` appears on serial output.
- The system SHALL pass a SIL test that verifies echo functionality via pipe-based serial I/O.

#### Reason
SIL 兼容确保 demo 可以在没有硬件的 CI 环境中自动验证。这是 CI/CD 流水线价值和 ASPICE 合规的直观证明。

#### GIVEN the demo firmware is cross-compiled for ESP32
##### WHEN CI Layer 2 SIL tests execute
##### THEN `qemu-sil-runner --elf build/demo-uart.elf` SHALL return `passed=True`
##### AND the SIL test report SHALL log `"Hello from yuleOSH Demo UART"`

---

## 3. 非功能性需求

- The system SHALL complete `yuleosh demo uart` project initialization in ≤ 2 seconds.
- The system SHALL produce a working firmware binary for ESP32 in ≤ 30 seconds on a typical developer machine.
- The demo project SHALL consume ≤ 32 KB flash and ≤ 8 KB RAM.
- The demo project README SHALL be ≤ 200 words and readable in 30 seconds.

---

## 4. SHALL 清单

| ID | 需求摘要 | 测试数 |
|:---|:---------|:------:|
| DEMO-UART-001.1 | `yuleosh demo uart` CLI 子命令存在 | ≥1 |
| DEMO-UART-001.2 | 创建 uart-demo/ 目录含 CMakeLists.txt + main.c | ≥3 |
| DEMO-UART-001.3 | 默认 ESP32 + IDF 构建 | ≥1 |
| DEMO-UART-001.4 | `--target` 多 MCU 支持 (MAY) | ≥0 |
| DEMO-UART-002.1 | UART 115200 8N1 默认配置 | ≥1 |
| DEMO-UART-002.2 | 启动输出 "Hello from yuleOSH Demo UART" | ≥2 |
| DEMO-UART-002.3 | 每 5s 心跳 "[yuleOSH] alive — {uptime}s" | ≥2 |
| DEMO-UART-002.4 | 启动完成输出 ready 提示 | ≥1 |
| DEMO-UART-002.5 | 可配波特率 (MAY) | ≥0 |
| DEMO-UART-003.1 | UART RX 字符接收 | ≥1 |
| DEMO-UART-003.2 | 单字符回显 "Echo: {char}" | ≥2 |
| DEMO-UART-003.3 | 字符串回显 "Line: {string}" | ≥2 |
| DEMO-UART-003.4 | 64 字节 RX 缓冲区 | ≥1 |
| DEMO-UART-004.1 | `--clean` 子命令 | ≥1 |
| DEMO-UART-004.2 | 删除前确认提示 | ≥1 |
| DEMO-UART-005.1 | QEMU ESP32 兼容 | ≥1 |
| DEMO-UART-005.2 | CI L2 SIL 测试通过 | ≥1 |
| DEMO-UART-005.3 | 串口断言 SIL 测试 | ≥2 |
| **SUM** | **19 SHALL 条款** | **≥23** |
