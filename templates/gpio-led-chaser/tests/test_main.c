/**
 * GPIO 流水灯 — 单元测试（宿主机 gcc + cmake/ctest）
 *
 * 覆盖（对应 docs/spec.md）：
 *   Req-001 流水掩码与 wrap
 *   Req-002 模式切换（CHASE/BOUNCE/BLINK_ALL/BREATHE）
 *   Req-003 tick 推进状态机
 *   Req-004 按钮消抖（单次按下只切一次）
 *   Req-006 HAL 桩（gpio_write / gpio_read）
 *
 * 通过 `#include "../src/main.c"` 直接复用参考实现（main 已被
 * LED_CHASER_UNIT_TEST 屏蔽），无需重复实现。
 */

#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "led_chaser.h"

/* 复用参考实现（main 在 LED_CHASER_UNIT_TEST 下被屏蔽） */
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
    printf("[led_chaser] unit tests\n");

    /* ---- Req-001：流水掩码 + wrap ---- */
    CHECK(led_chaser_chase_mask(0) == 0x01U);
    CHECK(led_chaser_chase_mask(7) == 0x80U);
    CHECK(led_chaser_chase_mask(8) == 0x01U);   /* 取模 wrap */
    CHECK(led_chaser_chase_mask(255) == 0x80U); /* 255%8=7 */

    /* ---- Req-003 + Req-001：init 后 PA0 亮，tick 推进并 wrap ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_CHASE);
    CHECK(led_chaser_current_mask() == 0x01U);
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x02U);
    for (int i = 0; i < 7; i++) {
        led_chaser_tick();
    }
    CHECK(led_chaser_current_mask() == 0x01U);  /* 8 步后回到 PA0 */

    /* ---- Req-002：BOUNCE 往返（两端折返，不越界） ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_BOUNCE);
    uint8_t first = led_chaser_current_mask();
    uint8_t prev = first;
    int monotonic_ok = 1;
    for (int i = 0; i < 20; i++) {
        led_chaser_tick();
        uint8_t cur = led_chaser_current_mask();
        if (cur == prev) { monotonic_ok = 0; }  /* 不应停留 */
        prev = cur;
    }
    CHECK(first != 0U);
    CHECK(monotonic_ok == 1);

    /* ---- Req-002：BLINK_ALL 同步闪烁（全亮/全灭交替） ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_BLINK_ALL);
    uint8_t b0 = led_chaser_current_mask();
    led_chaser_tick();
    uint8_t b1 = led_chaser_current_mask();
    CHECK(b0 != b1);
    CHECK((b0 == 0xFFU && b1 == 0x00U) || (b0 == 0x00U && b1 == 0xFFU));

    /* ---- Req-002：BREATHE 软件 PWM 呼吸（三角波亮度阶梯 0→4→1） ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_BREATHE);
    /* phase0..7 → lvl 0,1,2,3,4,3,2,1 → 低位 lvl 个 LED 点亮 */
    CHECK(led_chaser_current_mask() == 0x00U);  /* phase0 lvl0 = 全灭 */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x01U);  /* phase1 lvl1 */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x03U);  /* phase2 lvl2 */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x07U);  /* phase3 lvl3 */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x0FU);  /* phase4 lvl4（峰值） */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x07U);  /* phase5 lvl3（回落） */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x03U);  /* phase6 lvl2 */
    led_chaser_tick();
    CHECK(led_chaser_current_mask() == 0x01U);  /* phase7 lvl1 */

    /* ---- Req-006：HAL 桩读写 ---- */
    g_gpio_out[0] = 0x00U;
    gpio_write(0U, 3U, 1U);
    CHECK(g_gpio_out[0] == 0x08U);
    gpio_write(0U, 3U, 0U);
    CHECK(g_gpio_out[0] == 0x00U);
    gpio_write(0U, 0U, 1U);
    gpio_write(0U, 7U, 1U);
    CHECK(g_gpio_out[0] == 0x81U);
    /* 越界写应被忽略 */
    gpio_write(9U, 0U, 1U);
    CHECK(g_gpio_out[0] == 0x81U);

    /* ---- Req-004：按钮消抖（以毫秒计量，单次按下只切一次） ---- */
    led_chaser_init();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    g_gpio_in[1] = 0x00U;   /* PB0 拉低 = 按下（active-low） */
    led_chaser_handle_button(LED_DEBOUNCE_MS);   /* 稳定低 ≥50ms → 切换一次 */
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    /* 继续按住（再给 50ms）不应再切 */
    led_chaser_handle_button(LED_DEBOUNCE_MS);
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    /* 松开后再次按下应再切一次 */
    g_gpio_in[1] = 0x01U;   /* PB0 释放（high） */
    led_chaser_handle_button(LED_DEBOUNCE_MS);
    g_gpio_in[1] = 0x00U;   /* PB0 再次按下 */
    led_chaser_handle_button(LED_DEBOUNCE_MS);
    CHECK(led_chaser_get_mode() == LED_MODE_BLINK_ALL);

    /* ---- Req-004：消抖须以时间计量（<50ms 不稳定不切换） ---- */
    led_chaser_init();
    g_gpio_in[1] = 0x00U;
    led_chaser_handle_button(20U);   /* 仅 20ms，未达 50ms 阈值 */
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    led_chaser_handle_button(40U);   /* 累计 60ms → 跨越阈值 */
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);

    /* ---- 越界模式忽略（MISRA 防御）：当前为 BOUNCE，越界 set 应保持不变 ---- */
    led_chaser_set_mode((led_mode_t)LED_MODE_COUNT);
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);

    if (g_fail != 0) {
        printf("\n%d CHECK(s) FAILED\n", g_fail);
        return 1;
    }
    printf("\nALL LED CHASER TESTS PASSED\n");
    return 0;
}
