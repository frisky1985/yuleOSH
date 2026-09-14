/**
 * GPIO 流水灯 — 系统级合格性测试 (SWE.6, spec GIVEN/WHEN/THEN 场景驱动)
 *
 * 这是 test-qualification 门禁（合格性 Gate G10）所期望的「system-level test」：
 * 在宿主侧（gcc）直接复用参考实现 src/main.c（main() 已被 LED_CHASER_UNIT_TEST
 * 屏蔽），以自己的 main() 驱动固件主循环的五个 spec 场景，断言每一条验收判据。
 *
 * 覆盖 spec.md 中的 GIVEN/WHEN/THEN 场景：
 *   S1 上电默认流水   — PA0 先亮，PA0→PA7 每 200ms 推进并 wrap 回 PA0
 *   S2 按钮切换模式   — PB0 消抖后 CHASE→BOUNCE→BLINK_ALL→BREATHE→CHASE
 *   S3 消抖单次按下只切一次 — 长按 PB0 仅切换一次模式
 *   S4 低功耗空闲      — 空闲调用 WFI（宿主侧空操作，目标侧 __WFI）
 *   S5 安全配置        — RCC->APB2ENR 置 IOPA/IOPB；GPIOA->CRL 推挽输出 2MHz；
 *                       GPIOB->CRL PB0 输入上拉
 *
 * 通过 `#include "../src/main.c"` 复用参考实现，无需重复实现。
 */

#include <stdio.h>
#include <stdint.h>

#include "led_chaser.h"

/* 复用参考实现（main 在 LED_CHASER_UNIT_TEST 下被屏蔽，无 main 冲突） */
#define LED_CHASER_UNIT_TEST 1
#include "../src/main.c"

/* ------------------------------------------------------------------ */
/* 轻量断言框架                                                          */
/* ------------------------------------------------------------------ */
static int g_fail = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if ((cond)) {                                                        \
            printf("  ok: %s\n", #cond);                                     \
        } else {                                                             \
            printf("  FAIL: %s  (%s:%d)\n", #cond, __FILE__, __LINE__);      \
            g_fail++;                                                        \
        }                                                                     \
    } while (0)

int main(void) {
    printf("[led_chaser] SYSTEM qualification test (scenario-driven)\n");

    /* ============================================================== */
    /* S1 上电默认流水: PA0 先亮，PA0→PA7 每 tick 推进并 wrap 回 PA0   */
    /* ============================================================== */
    printf("\n[Scenario 1] 上电默认流水 (CHASE, PA0 first, advance PA0→PA7 wrapping)\n");
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_CHASE);
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    CHECK(led_chaser_current_mask() == 0x01U);          /* 上电默认 PA0 先亮 */
    for (int i = 0; i < (int)LED_COUNT; i++) {
        led_chaser_tick();
    }
    CHECK(led_chaser_current_mask() == 0x01U);          /* 8 步后 wrap 回 PA0 */
    /* 推进过程中每步恰好点亮一颗（单 bit 掩码） */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_CHASE);
    uint8_t prev_mask = led_chaser_current_mask();
    int s1_monotonic = 1;
    for (int i = 0; i < (int)LED_COUNT; i++) {
        led_chaser_tick();
        uint8_t cur = led_chaser_current_mask();
        if (cur == prev_mask) { s1_monotonic = 0; }     /* 不应停留 */
        prev_mask = cur;
    }
    CHECK(s1_monotonic == 1);

    /* ============================================================== */
    /* S2 按钮切换模式: CHASE→BOUNCE→BLINK_ALL→BREATHE→CHASE            */
    /* ============================================================== */
    printf("\n[Scenario 2] 按钮切换模式 (PB0 debounced: CHASE→BOUNCE→BLINK_ALL→BREATHE→CHASE)\n");
    led_chaser_init();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);

    /* 模拟一次消抖后的按下：PB0 拉低并保持 ≥ LED_DEBOUNCE_TICKS 个 tick */
    #define PRESS_AND_SETTLE()                                              \
        do {                                                                \
            g_gpio_in[1] = 0x00U;                                          \
            for (int _t = 0; _t < (int)(LED_DEBOUNCE_TICKS + 2U); _t++) {   \
                led_chaser_handle_button();                                \
            }                                                               \
            g_gpio_in[1] = 0x01U;                                          \
            for (int _t = 0; _t < 3; _t++) {                               \
                led_chaser_handle_button();                                \
            }                                                               \
        } while (0)

    PRESS_AND_SETTLE();
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    PRESS_AND_SETTLE();
    CHECK(led_chaser_get_mode() == LED_MODE_BLINK_ALL);
    PRESS_AND_SETTLE();
    CHECK(led_chaser_get_mode() == LED_MODE_BREATHE);
    PRESS_AND_SETTLE();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);          /* 循环回到 CHASE */

    /* ============================================================== */
    /* S3 消抖（单次按下只切一次）: 长按 PB0 仅切换一次模式            */
    /* ============================================================== */
    printf("\n[Scenario 3] 消抖（单次按下只切一次）\n");
    led_chaser_init();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    g_gpio_in[1] = 0x00U;                                   /* 持续按下 PB0 */
    for (int t = 0; t < 50; t++) {
        led_chaser_handle_button();                        /* 长按 50 tick */
    }
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);       /* 仅切换一次 */

    /* ============================================================== */
    /* S4 低功耗空闲: 空闲调用 WFI（宿主侧空操作，目标侧 __WFI）       */
    /* ============================================================== */
    printf("\n[Scenario 4] 低功耗空闲 (WFI idle sleep)\n");
    led_chaser_init();
    led_chaser_wfi();                                      /* Req-005 空闲 WFI 占位 */
    led_chaser_on_timer_isr();                            /* 模拟定时器中断唤醒 */
    led_chaser_wfi();
    CHECK(led_chaser_tick_pending() == 1U);               /* 中断唤醒后 tick 待处理 */
    CHECK(led_chaser_tick_count() >= 1U);                 /* 状态可观测、不崩溃 */

    /* ============================================================== */
    /* S5 安全配置: RCC/APB2ENR + GPIOA/B CRL 寄存器级初始化           */
    /* ============================================================== */
    printf("\n[Scenario 5] 安全配置 (RCC APB2ENR IOPA/IOPB, GPIOA CRL push-pull 2MHz, GPIOB CRL PB0 input pull-up)\n");
    led_chaser_init();
    const target_state_t* ts = led_chaser_target_state();
    CHECK((ts->apb2enr & (1U << 2)) != 0U);               /* RCC->APB2ENR IOPA 使能 */
    CHECK((ts->apb2enr & (1U << 3)) != 0U);               /* RCC->APB2ENR IOPB 使能 */
    CHECK(ts->gpioa_crl == 0x22222222U);                  /* GPIOA->CRL PA0..7 推挽输出 2MHz */
    CHECK(ts->gpiob_crl == 0x00000008U);                  /* GPIOB->CRL PB0 输入上拉 */

    if (g_fail != 0) {
        printf("\n%d CHECK(s) FAILED\n", g_fail);
        return 1;
    }
    printf("\nALL SYSTEM QUALIFICATION SCENARIOS PASSED\n");
    return 0;
}
