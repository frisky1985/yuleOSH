# demo-project — Body Control Module (BCM)

> **Template**: bcm | **MCU**: S32K312 (S32K3, ARM Cortex-M7) | **ASIL**: ASIL B
> **Generated**: 2026-11-10 23:30 by yuleOSH init

---

## 1. 项目简介

demo-project 是一个基于 AUTOSAR Classic Platform 的车身控制器 (Body Control Module) 项目，
使用 NXP S32K312 微控制器，ASIL 等级达到 ASIL B。

### 主要功能

- **门控 (Door Control)**: 门锁控制、车窗升降、后视镜调节、儿童锁
- **灯光 (Light Control)**: 近光灯、远光灯、转向灯、日间行车灯、雾灯
- **雨刮 (Wiper Control)**: 前雨刮、后雨刮、自动雨刮 (Rain Sensor)
- **电源 (Power Management)**: 电源模式管理、低功耗唤醒、KL15/KL30 监控

### MCU 规格

| 参数 | 值 |
|:-----|:----|
| MCU | S32K312 |
| Family | S32K3 |
| Architecture | ARM Cortex-M7 |
| Cores | 1 |
| Flash | 1024 KB |
| RAM | 192 KB |
| ASIL | ASIL B |

### BSW 模块 (12 个)


- **Mcu**

- **Dio**

- **Port**

- **Gpt**

- **Can**

- **Lin**

- **Spi**

- **Icu**

- **Pwm**

- **Adc**

- **Fls**

- **Wdg**


---

## 2. 通信矩阵

| 总线 | 类型 | 速率 | 用途 |
|:-----|:-----|:----:|:-----|
| CAN0 | CAN 2.0 | 500 kbps | 车身 CAN (Door/Light/Wiper) |
| LIN0 | LIN 2.1 | 19.2 kbps | 门模块通信 |
| LIN1 | LIN 2.1 | 19.2 kbps | 雨刮传感器 |

---

## 3. 软件架构

```
┌──────────────────────────────────────────────────────────┐
│                    RTE (Runtime Environment)              │
├──────────┬──────────┬──────────┬─────────────────────────┤
│Door_SWC  │Light_SWC │Wiper_SWC │  Power_SWC              │
│(Runnable)│(Runnable)│(Runnable)│  (Runnable + Mode Mgr)   │
├──────────┴──────────┴──────────┴─────────────────────────┤
│                    BSW Services                           │
│  Com / Dcm / Dem / EcuM / BswM / NvM / SchM              │
├──────────────────────────────────────────────────────────┤
│                    ECUAL                                  │
│  CanIf / CanTp / LinIf / LinTp / Fee / MemIf / WdgIf    │
├──────────────────────────────────────────────────────────┤
│                    MCAL                                   │
│  Mcu / Dio / Port / Gpt / Can / Lin / Spi / Icu / Pwm   │
│  Adc / Fls / Wdg                                         │
└──────────────────────────────────────────────────────────┘
```
