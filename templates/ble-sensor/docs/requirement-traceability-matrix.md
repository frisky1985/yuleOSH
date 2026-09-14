# BLE 传感器 — 需求追溯矩阵 (SWR Mapping Table)

需求 ID → 函数接口 → 测试 ID 的权威映射（供 `generate_lrm` 生成全链路矩阵）。

源码需求注解：`src/main.c` 顶部 `// @req Req-00x`
测试需求注解：`tests/system/scenario_test.c` 每场景 `// @req Req-00x` + `// @tests src/main.c: func()`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Req-001 正常上电 (2s 内全信道广播) | tests/system/scenario_test.c | sensor_read_temperature, sensor_get_temperature_x10 | ✅ |
| SWR-002 | Req-002 低电量告警 (电池百分比正确) | tests/system/scenario_test.c | battery_update_level, sensor_get_battery_percent | ✅ |
| SWR-003 | Req-003 配置更新 (GATT 写 interval 落 flash) | tests/system/scenario_test.c | gatt_on_config_write, config_compute_crc | ✅ |
| SWR-004 | Req-004 临界电量深睡 (<2.0V 100ms 内进入) | tests/system/scenario_test.c | hal_enter_deep_sleep | ✅ |

## Known Debt (T7 修复中, 不影响 G10 测试覆盖)
- `src/main.c` 的 `config_load` 在 HAL 桩 `hal_flash_read` 返回成功但数据无效时
  会无限递归 `sensor_init → config_load` (主机测试用合法默认配置绕过, 真实固件构建/运行会 segfault)。
  修复：默认配置自举 + 单次回退, 不再递归。
- 模板缺少 `ctest` 注册与真实断言计数 (当前断言为手工 `failed++`), 需补 `add_test` + 断言宏。
- spec / PRD / 开发计划的 SHALL 计数 (3/12/13) 互相矛盾, 需统一为 Req-001~004。
