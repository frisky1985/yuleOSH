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

    /* ---- Req-002：BREATHE 参考实现输出全亮 ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_BREATHE);
    CHECK(led_chaser_current_mask() == 0xFFU);

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

    /* ---- Req-004：按钮消抖（单次按下只切一次） ---- */
    led_chaser_init();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    g_gpio_in[1] = 0x00U;   /* PB0 拉低 = 按下（active-low） */
    for (int i = 0; i < (int)(LED_DEBOUNCE_MS + 5U); i++) {
        led_chaser_handle_button();
    }
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);   /* 仅切一次 */
    /* 继续按住不应再切 */
    for (int i = 0; i < 20; i++) {
        led_chaser_handle_button();
    }
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    /* 松开后再次按下应再切一次 */
    g_gpio_in[1] = 0x01U;   /* PB0 释放（high） */
    for (int i = 0; i < (int)LED_DEBOUNCE_MS; i++) {
        led_chaser_handle_button();
    }
    g_gpio_in[1] = 0x00U;   /* PB0 再次按下 */
    for (int i = 0; i < (int)(LED_DEBOUNCE_MS + 5U); i++) {
        led_chaser_handle_button();
    }
    CHECK(led_chaser_get_mode() == LED_MODE_BLINK_ALL);

    /* ---- 越界模式忽略（MISRA 防御） ---- */
    led_chaser_set_mode((led_mode_t)LED_MODE_COUNT);
    CHECK(led_chaser_get_mode() == LED_MODE_BLINK_ALL);

    if (g_fail != 0) {
        printf("\n%d CHECK(s) FAILED\n", g_fail);
        return 1;
    }
    printf("\nALL LED CHASER TESTS PASSED\n");
    return 0;
}
