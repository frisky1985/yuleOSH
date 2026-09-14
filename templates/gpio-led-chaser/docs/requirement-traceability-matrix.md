# GPIO 流水灯 — 需求追溯矩阵 (SWR Mapping Table)

需求 ID → 函数接口 → 测试 ID 的权威映射（供 `yuleosh.alm.traceability.generate_lrm`
生成需求全链路矩阵，并被方案评审门禁的「可追踪」项消费）。

源码需求注解：`src/main.c` / `src/led_chaser.h` 顶部 `// @req Req-00x`
测试需求注解：`tests/system/scenario_test.c` 每场景 `// @req Req-00x` + `// @tests src/main.c: func()`

| SHALL ID | Spec Source | Test File | Test Function | Status |
|---|---|---|---|---|
| SWR-001 | Req-001 上电默认流水 (PA0 先亮, PA0→PA7 每 200ms 推进并 wrap) | tests/system/scenario_test.c | led_chaser_init, led_chaser_set_mode, led_chaser_tick, led_chaser_current_mask | ✅ |
| SWR-002 | Req-002 按钮切换模式 (CHASE→BOUNCE→BLINK_ALL→BREATHE→CHASE) | tests/system/scenario_test.c | led_chaser_handle_button | ✅ |
| SWR-003 | Req-003 消抖 (单次按下只切一次) | tests/system/scenario_test.c | led_chaser_handle_button | ✅ |
| SWR-004 | Req-004 连续稳定低 tick 计数的消抖窗口 | tests/system/scenario_test.c | led_chaser_handle_button | ✅ |
| SWR-005 | Req-005 空闲 WFI 非忙等 (中断唤醒推进) | tests/system/scenario_test.c | led_chaser_wfi, led_chaser_on_timer_isr | ✅ |
| SWR-006 | Req-006 寄存器级安全配置 (RCC APB2ENR / GPIOA-B CRL) | tests/system/scenario_test.c | led_chaser_target_init, led_chaser_target_state | ✅ |
| SWR-007 | Req-007 定时器中断驱动主循环 (非忙等) | tests/system/scenario_test.c | led_chaser_on_timer_isr, led_chaser_tick_pending | ✅ |
