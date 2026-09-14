# CAN 总线 — 需求追溯矩阵 (SWR Mapping Table)

需求 ID → 函数接口 → 测试 ID 的权威映射（供 `generate_lrm` 生成全链路矩阵）。

源码需求注解：`src/main.c` 顶部 `// @req Req-00x`
测试需求注解：`tests/system/scenario_test.c` 每场景 `// @req Req-00x` + `// @tests src/main.c: func()`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Req-001 报文接收 (过滤器接受 0x150) | tests/system/scenario_test.c | can_gateway_init, can_add_filter | ✅ |
| SWR-002 | Req-002 周期发送 (ID 0x200, 1000ms, ≥4 次/5s) | tests/system/scenario_test.c | can_add_periodic_message, can_periodic_scheduler | ✅ |
| SWR-003 | Req-003 缓冲溢出 (满 256 丢弃最旧 + FIFO 日志导出) | tests/system/scenario_test.c | can_get_rx_count, can_get_overflow, can_export_log | ✅ |
| SWR-004 | Req-004 波特率配置 (UART "BAUD 500000") | tests/system/scenario_test.c | uart_process_command | ✅ |
| SWR-005 | SHALL bus-off 恢复 (ISO 11898-1 error passive→bus-off→自动恢复) | tests/system/scenario_test.c | can_register_bus_error, can_get_node_state, can_bus_off_recover | ✅ |
| SWR-006 | SHALL flash 配置持久化/恢复 (实际调用 hal_flash_read/write) | tests/system/scenario_test.c | config_save, config_load | ✅ |
| SWR-007 | SHALL 错误帧日志 (error flag bit 记录) | tests/system/scenario_test.c | can_log_error_frame | ✅ |
