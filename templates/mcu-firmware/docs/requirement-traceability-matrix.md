# MCU 固件 — 需求追溯矩阵 (SWR Mapping Table)

需求 ID → 函数接口 → 测试 ID 的权威映射（供 `generate_lrm` 生成全链路矩阵）。

源码需求注解：`src/main.cpp` 顶部 `// @req Req-00x`
测试需求注解：`tests/system/scenario_test.cpp` 每场景 `// @req Req-00x` + `// @tests src/main.cpp: func()`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Req-001 正常启动序列 (boot 完成, 调度器启动全部注册任务) | tests/system/scenario_test.cpp | config_load, scheduler_add_task, scheduler_run | ✅ |
| SWR-002 | Req-002 看门狗复位恢复 (RSR 检测, 进入安全模式) | tests/system/scenario_test.cpp | wdt_is_safe_mode | ✅ |
| SWR-003 | Req-003 出厂复位 (PA0 拉低擦除配置扇区) | tests/system/scenario_test.cpp | config_check_factory_reset | ✅ |
| SWR-004 | Req-004 损坏配置恢复 (CRC-16 不匹配检测并回退默认) | tests/system/scenario_test.cpp | config_load, config_crc | ✅ |
