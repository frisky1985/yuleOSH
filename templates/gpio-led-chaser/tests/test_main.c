/**
 * GPIO 流水灯 — 单元测试（宿主机 gcc + cmake/ctest）
 *
 * 覆盖（对应 docs/spec.md）：
 *   Req-001 流水掩码与 wrap
 *   Req-002 模式切换（CHASE/BOUNCE/BLINK_ALL/BREATHE）
 *   Req-003 tick 推进状态机
 *   Req-004 按钮消抖（按 tick 计数，单次按下只切一次）
 *   Req-006 HAL 桩（gpio_write / gpio_read）+ 寄存器级初始化镜像
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

    /* ---- Req-002：BREATHE 真·占空比 PWM（三角波 duty 0→max→0，时间分时） ---- */
    led_chaser_init();
    led_chaser_set_mode(LED_MODE_BREATHE);
    /* duty 函数：端点为 0，中点（LED_COUNT/2）满占空比，单调升/降 */
    CHECK(led_chaser_breathe_duty(0) == 0U);
    CHECK(led_chaser_breathe_duty(LED_COUNT / 2U) == LED_PWM_STEPS);
    CHECK(led_chaser_breathe_duty(LED_COUNT - 1U) == 0U);
    /* 一个完整呼吸周期（8 相位 × 8 载波 = 64 状态）内，掩码既出现全亮也出现全灭，
     * 即真实时间分时占空比呼吸，而非“LED 数量阶梯” */
    int saw_on = 0, saw_off = 0;
    for (int i = 0; i < 64; i++) {
        led_chaser_tick();
        uint8_t m = led_chaser_current_mask();
        if (m == 0xFFU) { saw_on = 1; }
        if (m == 0x00U) { saw_off = 1; }
    }
    CHECK(saw_on == 1);
    CHECK(saw_off == 1);

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

    /* ---- Req-004：按钮消抖（按 tick 计数，连续稳定低 LED_DEBOUNCE_TICKS 个 tick，
     *            单次按下只切一次） ---- */
    led_chaser_init();
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    g_gpio_in[1] = 0x00U;   /* PB0 拉低 = 按下（active-low） */
    led_chaser_handle_button();   /* 1st low tick：未达阈值，不切换 */
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    led_chaser_handle_button();   /* 2nd consecutive low tick：达到阈值，切一次 */
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    /* 继续按住不应再切（g_switched 锁） */
    led_chaser_handle_button();
    led_chaser_handle_button();
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);
    /* 松开后再按下应再切一次 */
    g_gpio_in[1] = 0x01U;   /* 释放 */
    led_chaser_handle_button();
    g_gpio_in[1] = 0x00U;   /* 再次按下 */
    led_chaser_handle_button();
    led_chaser_handle_button();
    CHECK(led_chaser_get_mode() == LED_MODE_BLINK_ALL);

    /* ---- Req-004：消抖须按“连续稳定低”计量（单次低 tick 不切换） ---- */
    led_chaser_init();
    g_gpio_in[1] = 0x00U;
    led_chaser_handle_button();   /* 仅 1 个低 tick，未达 LED_DEBOUNCE_TICKS 阈值 */
    CHECK(led_chaser_get_mode() == LED_MODE_CHASE);
    led_chaser_handle_button();   /* 第 2 个连续低 tick → 跨越阈值 */
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);

    /* ---- Req-006：寄存器级初始化（可编译镜像，供单测断言） ---- */
    led_chaser_init();
    const target_state_t* ts = led_chaser_target_state();
    CHECK(ts->apb2enr == 0x0CU);              /* RCC_APB2ENR_IOPA(bit2) | IOPB(bit3) */
    CHECK(ts->gpioa_crl == 0x22222222U);      /* PA0..7 推挽输出 2MHz */
    CHECK(ts->gpiob_crl == 0x00000008U);      /* PB0 输入上拉 */
    CHECK(ts->gpiob_odr == 0x00000001U);      /* PB0 上拉 */
    CHECK(ts->tim2_psc == 7199U);             /* 72MHz → 200ms：(7199+1)*(1999+1)/72e6=0.2s */
    CHECK(ts->tim2_arr == 1999U);

    /* ---- 越界模式忽略（MISRA 防御）：置为 BOUNCE 后越界 set 应保持不变 ---- */
    led_chaser_set_mode(LED_MODE_BOUNCE);
    led_chaser_set_mode((led_mode_t)LED_MODE_COUNT);
    CHECK(led_chaser_get_mode() == LED_MODE_BOUNCE);

    if (g_fail != 0) {
        printf("\n%d CHECK(s) FAILED\n", g_fail);
        return 1;
    }
    printf("\nALL LED CHASER TESTS PASSED\n");
    return 0;
}
