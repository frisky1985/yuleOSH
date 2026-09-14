# AUTOSAR BSW — 需求追溯矩阵 (SWR Mapping Table)

AUTOSAR 模板以「配置契约」承载可追溯性：`src/main.c` 依赖外部 yuleASR BSW 平台
(无法 host 编译), 但 `config/` 自包含, 由 `include/Std_Types.h` 桩驱动主机测试验证
时钟配置自洽。BSW 运行时行为 (UDS/DTC/NvM/调度循环) 由 yuleASR 集成台架在目标硬件覆盖。

源码需求注解：`src/main.c` 顶部 `// @req AUTOSAR-BSW: ...`
测试需求注解：`tests/system/scenario_test.c` `// @req AUTOSAR-BSW: ...` + `// @tests config/Mcu_Cfg.h`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Mcu 时钟配置契约 (CORE 120MHz / BUS 60MHz / PLL_REF 8MHz / SYS 120MHz) | tests/system/scenario_test.c | (config/Mcu_Cfg.h 时钟宏校验) | ✅ |
| SWR-002 | Mcu 复位检测使能 (MCU_RESET_DETECTION_ENABLE = STD_ON) | tests/system/scenario_test.c | (config/Mcu_Cfg.h 标志校验) | ✅ |
| SWR-003 | Mcu 看门狗禁用 (MCU_WATCHDOG_DISABLE = STD_ON) | tests/system/scenario_test.c | (config/Mcu_Cfg.h 标志校验) | ✅ |
| SWR-004 | Can/Com/Dcm/NvM 模块配置契约 (见 config/ 与 docs/spec.md §2) | config/ | (yuleASR 集成台架) | ✅ |
