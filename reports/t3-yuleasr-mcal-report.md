# T3 — yuleASR MCAL 补齐 + ECUAL 模板报告

> 生成日期: 2026-07-11
> 状态: ✅ 完成
> 关联: 专家评审 R3.2/R3.5/R3.7 — "yuleASR 73/94 模块无配置 stub"

---

## 一、概述

完成 yuleASR MCAL (21 模块) 和 ECUAL (29 模块) 的 stub 骨架文件生成，补齐 Phase 3 中缺失的 100 个配置文件（每个模块 .h + .c）。

### 文件统计

| 层级 | 模块数 | 文件数 (.h + .c) |
|------|--------|-------------------|
| MCAL | 21     | 42                |
| ECUAL | 29    | 58                |
| **合计** | **50** | **100**          |
| 模板整体 | —     | 111               |

### 未修改内容
- ❌ 未修改 `pyproject.toml` 的 `fail_under`
- ❌ 未修改已有测试逻辑
- ❌ 未修改已有 Phase 3 模板文件（`main.c`, `App_Swc`, `SchM_App`, `Rte_App`, `Std_Types.h`, `template.yaml`, `specs/spec.md`, `pipeline/config.yaml`）
- ❌ 未修改 `template.yaml`（其模块清单已完整）

---

## 二、MCAL 补齐（21 模块）

### 2.1 生成方式

生成脚本：`/tmp/gen_yuleasr_stubs.py`

每个模块在 `src/yuleosh/templates/yuleasr/src/mcal/<module>/` 下生成：
- `<Module>.h` — 头文件，包含 AUTOSAR 命名约定的类型定义和 API 声明
- `<Module>.c` — 源文件，包含函数骨架 + 默认返回值

### 2.2 完整模块清单

| # | 模块 | 目录 | API 数量 | 功能描述 |
|---|------|------|----------|----------|
| 1 | Mcu | mcal/mcu/ | 7 | 时钟/PLL/复位/模式管理 |
| 2 | Dio | mcal/dio/ | 8 | 数字 I/O 通道/端口 |
| 3 | Port | mcal/port/ | 6 | 引脚复用/方向/上下拉 |
| 4 | Gpt | mcal/gpt/ | 9 | 通用定时器通道 |
| 5 | Can | mcal/can/ | 8 | CAN 2.0 / CAN FD 控制器 |
| 6 | Lin | mcal/lin/ | 8 | LIN 2.2 主/从 |
| 7 | Spi | mcal/spi/ | 8 | SPI 主/从 同步/异步 |
| 8 | Adc | mcal/adc/ | 7 | 12-bit SAR ADC (HW触发) |
| 9 | Pwm | mcal/pwm/ | 7 | PWM 输出 |
| 10 | Icu | mcal/icu/ | 9 | 输入捕获 (周期/脉宽/边沿) |
| 11 | Ocu | mcal/ocu/ | 7 | 输出比较 |
| 12 | Fls | mcal/fls/ | 9 | Flash 扇区擦除/编程/读取 |
| 13 | Eep | mcal/eep/ | 8 | 外部 EEPROM 读写擦除 |
| 14 | Wdg | mcal/wdg/ | 6 | 内部看门狗超时/触发 |
| 15 | Eth | mcal/eth/ | 9 | 以太网 SGMII/RMII |
| 16 | I2C | mcal/i2c/ | 8 | I2C 主/从同步串行 |
| 17 | Uart | mcal/uart/ | 9 | UART 异步串行 (SCI) |
| 18 | Crypto | mcal/crypto/ | 9 | 硬件加密 AES/SHA/RSA/ECC |
| 19 | Fee | mcal/fee/ | 9 | Flash EEPROM 仿真 (MCAL级) |
| 20 | Flash | mcal/flash/ | 9 | Flash 底层操作 |
| 21 | RamTst | mcal/ramtst/ | 7 | RAM 自检 (March C-/Galpat) |

### 2.3 MCAL 模块共同特性

每个 MCAL stub 遵循 AUTOSAR 4.4 约定：
- `Module_Init(ConfigPtr)` — 初始化函数，设初始化标志
- `Module_DeInit(void)` — 反初始化，清除标志
- `Module_GetVersionInfo(VersionInfoPtr)` — 版本信息填充
- 模块专用 API（如 `Can_Write`, `Adc_ReadGroup` 等）
- 内部静态 `Module_Initialized` 标志
- 默认返回值：`Init` 类返回 `E_OK`，`Read` 类返回 `E_NOT_OK`（模拟无数据）
- `MainFunction` 类为空的 stub（无待处理事件）

---

## 三、ECUAL 模板（29 模块）

### 3.1 生成方式

每个模块在 `src/yuleosh/templates/yuleasr/src/ecual/<module>/` 下生成头文件和源文件。

ECUAL 是 yuleASR 的硬件抽象层，非 AUTOSAR 标准模块，但遵循 yuleASR 接口约定。

### 3.2 完整模块清单

| # | 模块 | 目录 | API 数量 | 功能描述 |
|---|------|------|----------|----------|
| 1 | CanIf | ecual/canif/ | 8 | CAN 接口 — PDU 路由 |
| 2 | CanTp | ecual/cantp/ | 7 | CAN TP — ISO 15765-2 传输层 |
| 3 | CanNm | ecual/cannm/ | 7 | CAN 网络管理 |
| 4 | CanSm | ecual/cansm/ | 5 | CAN 状态管理 |
| 5 | CanTrcv | ecual/cantrcv/ | 9 | CAN 收发器驱动 |
| 6 | LinIf | ecual/linif/ | 7 | LIN 接口 — 调度表和帧路由 |
| 7 | LinNm | ecual/linnm/ | 5 | LIN 网络管理 |
| 8 | LinSM | ecual/linsm/ | 5 | LIN 调度管理 |
| 9 | LinTp | ecual/lintp/ | 5 | LIN 传输层 |
| 10 | LinTrcv | ecual/lintrcv/ | 7 | LIN 收发器驱动 |
| 11 | DoIP | ecual/doip/ | 7 | 基于 IP 的诊断 — ISO 13400 |
| 12 | EthIf | ecual/ethif/ | 6 | 以太网接口 — PDU 路由 |
| 13 | EthSm | ecual/ethsm/ | 5 | 以太网状态管理 |
| 14 | EthTrcv | ecual/ethtrcv/ | 6 | 以太网收发器 (PHY) |
| 15 | FrIf | ecual/frif/ | 5 | FlexRay 接口 |
| 16 | FrTp | ecual/frtp/ | 5 | FlexRay TP — ISO 10681-2 |
| 17 | FiM | ecual/fim/ | 5 | 功能抑制管理 |
| 18 | Srp | ecual/srp/ | 5 | 同步实时协议 |
| 19 | Ea | ecual/ea/ | 7 | EEPROM 抽象 (NvM 后端) |
| 20 | IpHwAb | ecual/iphwab/ | 5 | I/O 硬件抽象 (统一 IO 信号接口) |
| 21 | IpduM | ecual/ipdum/ | 5 | I-PDU 多路复用器 |
| 22 | Fee | ecual/fee/ | 7 | Flash EEPROM 仿真 (ECUAL 级) |
| 23 | MemIf | ecual/memif/ | 8 | 内存抽象接口 |
| 24 | WdgIf | ecual/wdgif/ | 6 | 看门狗接口 (内/外部) |
| 25 | SomeIpIf | ecual/someipif/ | 5 | SOME/IP 接口 |
| 26 | SomeIpSd | ecual/someipsd/ | 7 | SOME/IP 服务发现 |
| 27 | Xcp | ecual/xcp/ | 6 | 通用标定协议 (CAN/Ethernet) |
| 28 | Dlt | ecual/dlt/ | 6 | 诊断日志和跟踪 |
| 29 | J1939Tp | ecual/j1939tp/ | 6 | J1939 传输层 (BAM/CMDT) |

### 3.3 ECUAL 模板共同特性

- `Module_Init(void)` / `Module_DeInit(void)` — 无配置参数 (ECUAL 级简化)
- `Module_GetVersionInfo(VersionInfoPtr)` — 版本信息
- 模块专用 API（如 `CanIf_Transmit`, `CanTrcv_SetTrcvMode`, `SomeIpSd_ServiceOffer` 等）
- 内部状态跟踪
- 所有读操作返回默认空值，写操作返回 `E_OK`
- `MainFunction` 类为空 stub

---

## 四、存放路径

所有文件路径相对于 `src/yuleosh/templates/yuleasr/src/`：

```
src/yuleosh/templates/yuleasr/src/
├── mcal/                       # MCAL: 21 modules
│   ├── adc/Adc.h, Adc.c
│   ├── can/Can.h, Can.c
│   ├── crypto/Crypto.h, Crypto.c
│   ├── dio/Dio.h, Dio.c
│   ├── eep/Eep.h, Eep.c
│   ├── eth/Eth.h, Eth.c
│   ├── fee/Fee.h, Fee.c
│   ├── flash/Flash.h, Flash.c
│   ├── fls/Fls.h, Fls.c
│   ├── gpt/Gpt.h, Gpt.c
│   ├── i2c/I2C.h, I2C.c
│   ├── icu/Icu.h, Icu.c
│   ├── lin/Lin.h, Lin.c
│   ├── mcu/Mcu.h, Mcu.c
│   ├── ocu/Ocu.h, Ocu.c
│   ├── port/Port.h, Port.c
│   ├── pwm/Pwm.h, Pwm.c
│   ├── ramtst/RamTst.h, RamTst.c
│   ├── spi/Spi.h, Spi.c
│   ├── uart/Uart.h, Uart.c
│   └── wdg/Wdg.h, Wdg.c
└── ecual/                      # ECUAL: 29 modules
    ├── canif/CanIf.h, CanIf.c
    ├── cannm/CanNm.h, CanNm.c
    ├── cansm/CanSm.h, CanSm.c
    ├── cantp/CanTp.h, CanTp.c
    ├── cantrcv/CanTrcv.h, CanTrcv.c
    ├── dlt/Dlt.h, Dlt.c
    ├── doip/DoIP.h, DoIP.c
    ├── ea/Ea.h, Ea.c
    ├── ethif/EthIf.h, EthIf.c
    ├── ethsm/EthSm.h, EthSm.c
    ├── ethtrcv/EthTrcv.h, EthTrcv.c
    ├── fee/Fee.h, Fee.c
    ├── fim/FiM.h, FiM.c
    ├── frif/FrIf.h, FrIf.c
    ├── frtp/FrTp.h, FrTp.c
    ├── ipdum/IpduM.h, IpduM.c
    ├── iphwab/IpHwAb.h, IpHwAb.c
    ├── j1939tp/J1939Tp.h, J1939Tp.c
    ├── linif/LinIf.h, LinIf.c
    ├── linnm/LinNm.h, LinNm.c
    ├── linsm/LinSM.h, LinSM.c
    ├── lintp/LinTp.h, LinTp.c
    ├── lintrcv/LinTrcv.h, LinTrcv.c
    ├── memif/MemIf.h, MemIf.c
    ├── someipif/SomeIpIf.h, SomeIpIf.c
    ├── someipsd/SomeIpSd.h, SomeIpSd.c
    ├── srp/Srp.h, Srp.c
    ├── wdgif/WdgIf.h, WdgIf.c
    └── xcp/Xcp.h, Xcp.c
```

---

## 五、template.yaml 状态

`template.yaml` 中已有完整的模块清单（未修改）：

```yaml
yuleasr:
  modules_mcal: [Mcu, Dio, Port, Gpt, Can, Lin, Spi, Icu, Ocu, Pwm, Adc, Fls, Eep, Wdg, Eth, I2C, Uart, Crypto, Fee, Flash, RamTst]        # 21
  modules_ecual: [CanIf, CanNm, CanSm, CanTp, CanTrcv, LinIf, LinNm, LinSM, LinTp, LinTrcv, DoIP, EthIf, EthSm, EthTrcv, FrIf, FrTp, FiM, Srp, Ea, IpHwAb, IpduM, Fee, MemIf, WdgIf, SomeIpIf, SomeIpSd, Xcp, Dlt, J1939Tp]  # 29
  modules_services: [...]  # 44 (未改动)
```

---

## 六、验证状态

### 测试通过
- ✅ 148 of 148 template/autosar 相关测试通过
- ✅ 生成脚本确认所有 50 模块的 .h/.c 文件存在
- ✅ 模块计数：MCAL 21 ✓, ECUAL 29 ✓, 合计 50 ✓
- ✅ 文件计数：100 个 stub 文件 + 11 个原有文件 = 111 个模板文件

### 预存失败（非本次变更引起）
- `test_ci_fixes_p0_p1.py::test_c_coverage_gate_in_stages` — CI 层预期 `c-coverage-gate` 字符串未实现
- `test_ci/test_e2e_report_pipeline.py::test_cppcheck_driver_parse_c2012_format` — cppcheck 驱动解析问题
- `test_product_v1.py::test_tg_req_005_src_files` — 期望 CMakeLists.txt，yuleASR 使用 Makefile

### 约定遵守
- ❌ 未修改 `pyproject.toml` 的 `fail_under`
- ❌ 未修改已有测试逻辑
- ❌ 未修改已有 Phase 3 模板文件

---

## 七、后续建议

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P1 | MCAL 配置头文件生成 | 在 `init-autosar` 时由 configurator 生成 `Mcu_Cfg.h`, `Can_Cfg.h` 等 |
| P1 | Services 层 stub 补齐 | 44 个 Services 模块的 stub (Com, Dcm, Dem, EcuM, BswM, NvM 等) |
| P2 | CMakeLists.txt 支持 | 满足 `test_tg_req_005` 期望 |
| P2 | yuleASR 源码集成 | 将 stub 替换为实际 yuleASR 驱动调用 |
