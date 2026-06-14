# yuleOSH UART Demo — STM32F4 ↔ ESP32

> 3分钟跑通端到端UART通信全流程

## 概述

这个demo展示了**嵌入式AI全流程**的一块核心拼图：**MCU间的UART通信**。

| 组件 | 芯片 | 职责 |
|------|------|------|
| **STM32F4** | Cortex-M4 @ 168 MHz | 传感器/电机控制器，发送数据帧 |
| **ESP32** | Xtensa LX6 | UART桥接，解析帧协议，转发到WiFi/MQTT |
| **Host** | 你的电脑 | 编译&仿真验证（无需硬件） |

## 快速开始（3分钟）

### 第0步：环境检查

```bash
# 检查 C 编译器
gcc --version

# 检查 CMake
cmake --version

# 检查 arm-none-eabi-gcc（可选，交叉编译）
arm-none-eabi-gcc --version 2>/dev/null || echo "⚠️  未安装，跳过STM32交叉编译"
```

### 第1步：主机编译验证（无需硬件）

```bash
cd demos/uart
mkdir -p build_host && cd build_host
cmake -DTARGET=host ..
make
./uart_demo_host
```

**预期输出最后一行：**
```
  ╔══════════════════════════════════════════════════════╗
  ║   ✅  UART Communication Successful!                ║
  ║   STM32F4 ↔ ESP32 bridge is working correctly.     ║
  ╚══════════════════════════════════════════════════════╝
```

### 第2步：STM32交叉编译（可选，需 arm-none-eabi-gcc）

```bash
cd demos/uart
mkdir -p build_stm32 && cd build_stm32
cmake -DTARGET=stm32f4 -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain_stm32.cmake ..
make
# 输出: uart_demo_stm32.elf + uart_demo_stm32.hex
# 用 ST-Link 烧录: st-flash write uart_demo_stm32.hex 0x08000000
```

### 第3步：ESP-IDF 编译（可选，需 ESP-IDF 环境）

```bash
cd demos/uart/esp32
idf.py set-target esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash monitor
```

## 项目结构

```
demos/uart/
├── README.md                 ← 你正在看这里
├── CMakeLists.txt            ← 统一构建（host/stm32/esp32三合一）
├── demo_host.c               ← Host仿真运行器（主入口）
│
├── stm32/
│   ├── usart_driver.h        ← STM32F4 USART 驱动头文件
│   ├── usart_driver.c        ← STM32F4 USART 驱动实现
│   └── platform_stm32.c      ← STM32平台抽象层
│
├── esp32/
│   ├── uart_bridge.h         ← ESP32 UART桥接头文件（帧协议）
│   ├── uart_bridge.c         ← ESP32 UART桥接实现
│   └── platform_esp32.c      ← ESP32平台抽象层
│
└── cmake/
    ├── toolchain_stm32.cmake  ← STM32交叉编译工具链
    └── toolchain_esp32.cmake  ← ESP32交叉编译工具链
```

## 帧协议

```
STM32 → ESP32:  <STX><LEN><PAYLOAD><CRC><ETX>
ESP32 → STM32:  <STX><CMD_ID><PAYLOAD><CRC><ETX>

STX = 0x02, ETX = 0x03

示例:
  02 0A 48 65 6C 6C 6F 0A 00 D7 03
  STX LEN H  e  l  l  o  \n \0 CRC ETX
```

## 通信成功后的下一步

```bash
# 查看yuleOSH整体demo
yuleosh demo --help

# 查看项目统计
yuleosh stats

# 启动dashboard
yuleosh ui
```

## 故障排除

| 症状 | 原因 | 解决 |
|------|------|------|
| `make: command not found` | 未安装编译工具 | `brew install cmake make gcc` |
| `CRC mismatch` | 波特率不匹配 | 确保STN32和ESP32用同一波特率 |
| 无输出 | 串口线未连接 | 检查TX↔RX交叉连接 |
