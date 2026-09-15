# BLE 传感器 — 需求追溯矩阵 (SWR Mapping Table)

需求 ID → 函数接口 → 测试 ID 的权威映射（供 `generate_lrm` 生成全链路矩阵）。

源码需求注解：`src/main.c` 顶部 `// @req Req-00x`
测试需求注解：`tests/system/scenario_test.c` 每场景 `// @req Req-00x` + `// @tests src/main.c: func()`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Req-001 BLE 广播 (正常上电 2s 内全信道广播) | tests/system/scenario_test.c | test_ble_advertising_default_interval, test_ble_advertising_interval_clamping, test_ble_advertising_channel_support | ✅ |
| SWR-002 | Req-002 温度传感 (温度读取精度 ±0.5°C) | tests/system/scenario_test.c | test_temperature_read_normal, test_temperature_accuracy_range, test_temperature_out_of_range | ✅ |
| SWR-003 | Req-003 电池管理 (低电量告警 + 临界电量深睡) | tests/system/scenario_test.c | test_battery_update_level, test_battery_critical_deep_sleep, test_battery_percent_range | ✅ |
| SWR-004 | Req-004 配置与持久化 (GATT 写 interval 落 flash) | tests/system/scenario_test.c | test_config_load_defaults, test_config_save_and_crc, test_gatt_config_write_interval | ✅ |

## Known Debt (不影响 G10 测试覆盖)
- `src/main.c` 的 `config_load` 在 HAL 桩 `hal_flash_read` 返回成功但数据无效时
  会无限递归 `sensor_init → config_load` (主机测试用合法默认配置绕过, 真实固件构建/运行会 segfault)。
  修复：默认配置自举 + 单次回退, 不再递归。
- Eddystone-TLM 电量字段按公开规范为电池电压 (uint16 mV), 与 spec Req-003 L30「百分比 0-100%」
  存在规范冲突; demo 模板以 `sensor_get_battery_percent()` 另暴露百分比, 属已知 spec/标准不一致。
- spec / PRD / 开发计划的 SHALL 计数需统一为官方单一事实源 (spec 全文 26 条:
  23 SHALL + 2 SHOULD + 1 MAY, 含 10 条场景 SHALL), 避免 PRD 头自报 13 造成的追溯基线矛盾。
