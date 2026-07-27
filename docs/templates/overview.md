# ECU 模板总览

> 量产 AUTOSAR ECU 快速启动模板库 — `yuleosh init --template <name>`

---

## 可用模板

| 模板 | 名称 | MCU | ASIL 等级 | SWCs | BSW 模块 |
|:-----|:-----|:---:|:---------:|:----:|:--------:|
| `bcm` | 车身控制器 | S32K312 | QM~ASIL B | 4 | 12 |
| `dcu` | 域控制器 | S32K344 | ASIL B | 5 | 18 |
| `vcu` | 整车控制器 | S32K324 | ASIL C~D | 5 | 14 |
| `bms` | 电池管理系统 | S32K314 | ASIL C~D | 5 | 14 |
| `eps` | 电动助力转向 | S32K312 | ASIL D | 4 | 12 |

---

## 使用方法

```bash
# 基础用法
yuleosh init --template bcm --name my-bcm --output ./projects

# 指定 MCU 和 ASIL 等级
yuleosh init --template vcu --name powertrain-vcu --mcu S32K324 --asil ASIL_D

# 在当前目录创建
yuleosh init --template eps --name my-eps
```

### 参数说明

| 参数 | 默认值 | 说明 |
|:-----|:-------|:-----|
| `--template, -t` | (必填) | 模板名称: bcm, dcu, vcu, bms, eps |
| `--name` | `<template>-project` | 项目名称(用于命名空间) |
| `--mcu` | 模板默认 MCU | 目标 MCU 型号 |
| `--asil` | 模板默认 ASIL | 安全等级 |
| `--output, -o` | 当前目录 | 输出父目录 |

---

## 模板产出结构

```
<project-name>/
├── docs/
│   ├── project-context.md        # 项目简介 (MCU/ASIL/架构图)
│   ├── spec.md                   # SHALL 需求 (20~30条领域特定)
│   ├── safety-concept.md         # HARA + Safety Goals
│   └── safety-architecture.md    # DFA + MPU + FMEDA 骨架
├── src/
│   ├── app/
│   │   ├── <SWC>*.c              # SWC 骨架代码
│   │   └── <SWC>*.h              # SWC 头文件
│   └── bsw/
│       └── Bsw_Cfg.h             # BSW 配置存根
├── tests/
│   └── unit/
│       └── test_*.c              # 单元测试骨
├── ci-config.yaml                # CI 配置 (MISRA/coverage/gate)
├── yuleosh.yaml                  # 项目元数据
├── .gitignore
└── README.md
```

---

## 模板内容对比

| 领域 | BCM | DCU | VCU | BMS | EPS |
|:-----|:---:|:---:|:---:|:---:|:---:|
| SHALL 需求数 | ~30 | ~20 | ~22 | ~18 | ~20 |
| HARA Hazards | 4 | 3 | 3 | 4 | 3 |
| Safety Goals | 4 | 4 | 4 | 5 | 4 |
| CI 覆盖率要求 | 70% | 65% | 75% | 70% | 80% |
| E2E 保护 | ✅ | ✅ | ✅ | ✅ | ✅ |
| MPU 分区 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 看门狗 | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 下一步

- [自定义模板](customize.md) — 基于现有模板创建定制版本
- 运行 `yuleosh spec validate docs/spec.md` 验证需求
- 运行 `yuleosh ci run 1` 触发 L1 CI
