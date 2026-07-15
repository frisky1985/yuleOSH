# Phase 3 — yuleASR 深度集成报告

> 生成日期: 2026-07-10
> 状态: ✅ 完成

---

## 一、概述

完成了 yuleASR AUTOSAR BSW 平台到 yuleOSH 的深度集成。

### 集成内容
1. **内置模板** — `src/yuleosh/templates/yuleasr/` 作为 yuleOSH 内置模板
2. **项目模板** — `templates/autosar/` 作为独立可构建的项目示例
3. **CLI 命令** — `yuleosh init-autosar <project-name>` 一键生成带完整 BSW 栈的 AUTOSAR 项目

---

## 二、模板结构

### 2.1 内置模板 (`src/yuleosh/templates/yuleasr/`)

```
src/yuleosh/templates/yuleasr/
├── template.yaml           # 模板元数据 (含 21+29+44 模块清单)
├── specs/spec.md           # AUTOSAR OpenSpec 模板 (7 章节, 含 All MCAL/ECUAL/Services 需求)
├── pipeline/config.yaml    # Pipeline 配置 (含 yuleASR BSW 审查 gate)
├── src/
│   ├── main.c              # BSW 完整初始化序列 (MCAL → ECUAL → Services → RTE → App)
│   ├── App_Swc.h           # SW-C 接口定义 (SR/CS Port)
│   ├── App_Swc.c           # SW-C 实现 (含 Dem/E2E 集成)
│   ├── SchM_App.h/c        # 调度管理实现 (1ms/10ms/100ms/1000ms)
│   ├── Rte_App.h           # RTE 接口 (placeholder, 正常由 RTE 生成器生成)
│   └── Std_Types.h         # AUTOSAR 标准类型
├── tests/.gitkeep
└── .gitignore
```

### 2.2 项目模板 (`templates/autosar/`)

```
templates/autosar/
├── Makefile                # 完整构建系统 (arm-none-eabi-gcc, 支持 YULEASR_HOME)
├── docs/spec.md            # OpenSpec 模板
├── src/
│   ├── main.c              # 应用入口 (BSW 初始化和主循环)
├── config/
│   ├── Mcu_Cfg.h/c         # MCU 时钟配置 (S32K312: 120MHz core, 60MHz bus)
│   ├── Dio_Cfg.h/c         # DIO 通道配置
│   ├── Port_Cfg.h          # Port 引脚配置
│   ├── Gpt_Cfg.h           # GPT 定时器配置
│   ├── Can_Cfg.h           # CAN 控制器配置 (500kbps/2Mbps FD)
│   └── BswM_Cfg.h          # BSW 模式管理配置
├── linker/
│   └── s32k312.ld          # S32K312 链接脚本 (512K PFLASH, 256K DFLASH, 128K SRAM)
├── tests/
│   └── test_main.c         # 单元测试框架
└── .gitignore
```

---

## 三、CLI 用法

### 3.1 新的 CLI 命令

```bash
# 从 yuleasr 内置模板创建 AUTOSAR BSW 项目
yuleosh init-autosar <project-name> [--dir <parent-dir>] [--yuleasr-home <path>]

# 示例
yuleosh init-autosar my-ecu --dir ~/projects
```

### 3.2 通过已有模板系统使用

```bash
# 列出所有可用模板
yuleosh template list

# 从 yuleasr 模板创建项目
yuleosh project init --template yuleasr my-ecu
```

### 3.3 生成的项目结构

```
my-ecu/
├── yuleosh.yaml             # 项目元数据 (含 BSW 模块清单)
├── docs/spec.md             # AUTOSAR OpenSpec 规范
├── pipeline/config.yaml     # Pipeline 配置
├── src/                     # 应用源码
│   ├── main.c
│   ├── App_Swc.h/c
│   ├── SchM_App.h/c
│   ├── Rte_App.h
│   └── Std_Types.h
├── config/                  # BSW 配置头文件
│   ├── Mcu_Cfg.h
│   ├── Dio_Cfg.h
│   ├── Port_Cfg.h
│   └── Can_Cfg.h
├── linker/                  # 链接脚本目录
│   └── s32k312.ld           # S32K312 链接脚本
├── arxml/                   # ARXML 描述符目录
├── tests/                   # 测试目录
└── .gitignore
```

### 3.4 构建生成的 AUTOSAR 项目

```bash
export YULEASR_HOME=/path/to/yuleASR
cd my-ecu
make                    # 构建
make flash              # 通过 OpenOCD 烧录
make flash-jlink        # 通过 JLink 烧录
make debug              # GDB 调试
make clean              # 清理
```

---

## 四、yuleASR BSW 栈集成详情

### MCAL (21 模块) — 微控制器抽象层

| 模块 | 功能 | 配置 stub |
|------|------|-----------|
| Mcu | 时钟/PLL/复位 | Mcu_Cfg.h |
| Dio | GPIO 读写 | Dio_Cfg.h |
| Port | 引脚方向/复用/上下拉 | Port_Cfg.h |
| Gpt | 定时器通道 | Gpt_Cfg.h |
| Can | CAN 2.0 / CAN FD | Can_Cfg.h |
| Lin | LIN 2.2 主/从 | — |
| Spi | SPI 主/从同步/异步 | — |
| Adc | ADC 12bit 硬件触发 | — |
| Pwm | PWM 输出 | — |
| Icu | 输入捕获 | — |
| Ocu | 输出比较 | — |
| Fls | Flash 驱动 | — |
| Eep | EEPROM 驱动 | — |
| Wdg | 看门狗 | — |
| Eth | 以太网 (SGMII/RMII) | — |
| I2C | I2C 主/从 | — |
| Uart | UART 收发 | — |
| Crypto | 硬件加密加速 | — |
| Fee | Flash EEPROM 仿真 (MCAL 级) | — |
| Flash | Flash 底层操作 | — |
| RamTst | RAM 自检 | — |

### ECUAL (29 模块) — ECU 抽象层

| 模块 | 功能 |
|------|------|
| CanIf | CAN 接口 — PDU 路由 |
| CanTp | CAN TP — ISO 15765-2 传输层 |
| CanNm | CAN 网络管理 |
| CanSm | CAN 状态管理 |
| CanTrcv | CAN 收发器驱动 |
| LinIf | LIN 接口 |
| LinNm | LIN 网络管理 |
| LinSM | LIN 调度管理 |
| LinTp | LIN 传输层 |
| LinTrcv | LIN 收发器驱动 |
| DoIP | 基于 IP 的诊断 — ISO 13400 |
| EthIf | 以太网接口 |
| EthSm | 以太网状态管理 |
| EthTrcv | 以太网收发器 |
| FrIf | FlexRay 接口 |
| FrTp | FlexRay TP |
| FiM | 功能抑制管理 |
| Srp | 同步实时协议 |
| Ea | EEPROM 抽象 |
| IpHwAb | I/O 硬件抽象 |
| IpduM | I-PDU 多路复用器 |
| Fee | Flash EEPROM 仿真 (ECUAL 级) |
| MemIf | 内存抽象接口 |
| WdgIf | 看门狗接口 |
| SomeIpIf | SOME/IP 接口 |
| SomeIpSd | SOME/IP 服务发现 |
| Xcp | 通用标定协议 |
| Dlt | 诊断日志和跟踪 |
| J1939Tp | J1939 传输层 |

### Services (44 模块) — 服务层

| 模块 | 功能 |
|------|------|
| Com | 通信栈 |
| Dcm | 诊断通信管理 — UDS (ISO 14229) |
| Dem | 诊断事件管理 — DTC (ISO 15031-6) |
| Det | 预开发错误跟踪 |
| EcuM | ECU 管理 |
| BswM | BSW 模式管理 |
| SchM | 调度管理 |
| NvM | NVRAM 管理器 |
| ComM | 通信管理 |
| PduR | PDU 路由器 |
| CanM | CAN 网络管理 |
| CanSm | CAN 状态管理 |
| LinM | LIN 网络管理 |
| LinSm | LIN 状态管理 |
| LinTp | LIN 传输层 |
| EthSm | 以太网状态管理 |
| FiM | 功能抑制管理 |
| IpduM | I-PDU 多路复用器 |
| E2E | 端到端通信保护 |
| Crc | CRC 计算 |
| CryIf | 加密接口 |
| Csm | 加密服务管理 |
| KeyM | 密钥管理 |
| SecOC | 安全车载通信 |
| SoAd | Socket 适配器 |
| SomeIp | SOME/IP 协议 |
| SomeIpTp | SOME/IP 传输层 |
| SomeIpXf | SOME/IP 转换 |
| StbM | 同步时间基础管理 |
| WdgM | 看门狗管理 |
| Xcp | 标定协议 |
| Dlt | 诊断日志和跟踪 |
| J1939Nm | J1939 网络管理 |
| J1939Tp | J1939 传输层 |
| UdpNm | UDP 网络管理 |
| MemIf | 内存抽象接口 |
| Mem | 内存管理器 |
| Nm | 通用网络管理 |
| SwC | 软件组件支持 |
| LnTm | LIN 传输管理 |
| Mqtt | MQTT 客户端 |
| RAMSafety | RAM 安全测试 |
| DoCan | CAN 诊断 |
| EcuC | ECU 配置 |

---

## 五、集成方式

### 方式 A: 通过内置模板系统
```bash
yuleosh init-autosar my-project
```
内部调用 `yuleosh.templates` 模块的 `cmd_template_init` 和 `resolve_template`。

### 方式 B: 手动从模板拷贝
```bash
cp -r path/to/yuleOSH/templates/autosar my-project
```

### 模板搜索优先级 (TG-REQ-002)
1. 项目本地: `<project_root>/.yuleosh/templates/<name>/`
2. 用户本地: `~/.yuleosh/templates/<name>/`
3. 内置: `<package>/yuleosh/templates/<name>/`

---

## 六、下一步计划

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | ARXML 导入 | `yuleosh init-autosar --arxml <file>` 从 ARXML 生成项目 |
| P0 | yuleASR RTE 生成器集成 | 在 init 后自动调用 RTE generator |
| P1 | 配置 GUI 集成 | 在 init 时调用 yuleASR configurator 生成配置 |
| P1 | 多 MCU 支持 | 模板支持 S32K3, S32K1, STM32 等多平台 |
| P1 | BSW 模块选择 | `--bsw com,dcm,nvm` 选择性初始化部分模块 |
| P2 | MISRA 检查自动化 | 在 CI L2 中自动调用 yuleASR MISRA 检查 |
| P2 | 单元测试模板 | 自动生成 Dem/Dcm/EcuM 等模块的 mock 测试 |

---

## 七、完成检查清单

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | yuleASR 项目模板完整性 | ✅ |
| 2 | CLI init-autosar 命令 | ✅ |
| 3 | 模板可被 `yuleosh project init --template yuleasr` 发现 | ✅ |
| 4 | 生成的 AUTOSAR 项目结构完整 | ✅ |
| 5 | spec.md 包含全部 21+29+44 模块需求 | ✅ |
| 6 | Makefile 支持 YULEASR_HOME 引用 | ✅ |
| 7 | 链接脚本适用 S32K312 | ✅ |
| 8 | SW-C 示例代码含 Dem/E2E 集成 | ✅ |
| 9 | BSW 初始化序列遵循 AUTOSAR 规范顺序 | ✅ |
| 10 | 模板元数据含完整模块清单 | ✅ |
