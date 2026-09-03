/**
 * GPIO 流水灯 (LED Chaser) — 参考实现（宿主机可编译 / 可单测）
 *
 * 实现（需求自拟，对应 docs/spec.md）：
 *   Req-001 8 路流水灯（PA0..PA7），单向 wrap
 *   Req-002 模式切换 CHASE/BOUNCE/BLINK_ALL/BREATHE（PB0 按钮）
 *   Req-003 定时器驱动、禁止忙等（宿主侧用 tick 计数模拟）
 *   Req-004 按钮软件消抖 50 ms
 *   Req-005 空闲 WFI（宿主侧空操作）
 *   Req-006 GPIO 时钟使能 + 推挽输出 + 上拉输入（目标侧寄存器注释）
 *
 * 目标硬件：STM32F103C8T6（Blue Pill, Cortex-M3）
 * Toolchain：ARM GCC；宿主 build/test 用 gcc + cmake + ctest
 *
 * 设计约定：pattern 状态机逻辑全部为纯函数 / 无寄存器依赖，便于宿主 ctest
 * 覆盖；真实寄存器初始化序列由 `development` / `codegen-deploy` 步生成并覆盖本文件。
 */

#include <stdint.h>
#include <stdbool.h>

#include "led_chaser.h"

/* ------------------------------------------------------------------ */
/* 宿主 HAL 模拟（目标侧替换为 RCC/GPIOx 寄存器）                      */
/* ------------------------------------------------------------------ */
uint8_t g_gpio_out[3] = {0U, 0U, 0U};   /* port A=0, B=1, C=2 */
uint8_t g_gpio_in[3]  = {0U, 0U, 0U};

void gpio_write(uint8_t port, uint8_t pin, uint8_t val) {
    if (port >= 3U || pin >= 8U) {
        return;   /* 防御：越界写忽略（MISRA 越界防护） */
    }
    if (val != 0U) {
        g_gpio_out[port] = (uint8_t)(g_gpio_out[port] | (uint8_t)(1U << pin));
    } else {
        g_gpio_out[port] = (uint8_t)(g_gpio_out[port] & (uint8_t)~(1U << pin));
    }
}

uint8_t gpio_read(uint8_t port, uint8_t pin) {
    if (port >= 3U || pin >= 8U) {
        return 0U;
    }
    return (uint8_t)((g_gpio_in[port] >> pin) & 0x1U);
}

/* ------------------------------------------------------------------ */
/* 模式状态（volatile：目标侧由 TIM2/SysTick/EXTI ISR 写）            */
/* ------------------------------------------------------------------ */
static uint8_t   g_pos = 0U;            /* 当前 LED 位置 0..7 */
static uint8_t   g_dir = 1U;            /* BOUNCE 方向：1=右, 0=左 */
static led_mode_t g_mode = LED_MODE_CHASE;
static uint32_t  g_tick_ms = 0U;        /* 累计 tick（用于周期） */

/* ------------------------------------------------------------------ */
/* 纯函数：pattern 掩码计算（Req NFR-确定性，宿主可单测）             */
/* ------------------------------------------------------------------ */

/** 单向流水：pos 处单 bit 点亮，pos>=8 取模 wrap */
uint8_t led_chaser_chase_mask(uint8_t pos) {
    uint8_t p = pos;
    if (p >= LED_COUNT) {
        p = (uint8_t)(p % LED_COUNT);
    }
    return (uint8_t)(1U << p);
}

/** 往返流水：到 7 折返、到 0 折返；p_dir 回写新方向 */
uint8_t led_chaser_bounce_mask(uint8_t pos, uint8_t *p_dir) {
    uint8_t p = pos;
    if (p >= (LED_COUNT - 1U)) {
        p = (uint8_t)(LED_COUNT - 1U);
        if (p_dir != 0) { *p_dir = 0U; }   /* 到顶→改向左 */
    }
    if (p == 0U) {
        if (p_dir != 0) { *p_dir = 1U; }   /* 到底→改向右 */
    }
    return (uint8_t)(1U << p);
}

/* ------------------------------------------------------------------ */
/* 生命周期 / 控制                                                      */
/* ------------------------------------------------------------------ */

void led_chaser_init(void) {
    g_pos = 0U;
    g_dir = 1U;
    g_mode = (led_mode_t)LED_DEFAULT_MODE;
    g_tick_ms = 0U;
    /* 目标侧（注释，供 development 步参考）：
     *   RCC->APB2ENR |= RCC_APB2ENR_IOPA | RCC_APB2ENR_IOPB;   // Req-006 时钟使能
     *   GPIOA->CRL = 0x22222222;   // PA0..7 输出推挽 2MHz
     *   GPIOB->CRL = 0x88888888;   // PB0 输入上拉（ODR 对应位写 1）
     *   GPIOB->ODR |= (1U << 0);
     */
}

uint8_t led_chaser_current_mask(void) {
    uint8_t mask = 0U;
    switch (g_mode) {
        case LED_MODE_CHASE:
            mask = led_chaser_chase_mask(g_pos);
            break;
        case LED_MODE_BOUNCE:
            mask = led_chaser_bounce_mask(g_pos, &g_dir);
            break;
        case LED_MODE_BLINK_ALL:
            mask = (g_pos & 1U) ? 0xFFU : 0x00U;
            break;
        case LED_MODE_BREATHE:
            /* 参考实现：全亮占位；真实 PWM 占空比由 TIMx CCR 决定（见差距分析 deviation） */
            mask = 0xFFU;
            break;
        default:
            mask = 0U;
            break;
    }
    return mask;
}

void led_chaser_set_mode(led_mode_t m) {
    if (m < LED_MODE_COUNT) {
        g_mode = m;
    }
    /* 越界模式忽略（MISRA 防御） */
}

led_mode_t led_chaser_get_mode(void) {
    return g_mode;
}

/** 推进一个 pattern step（Req-003：由定时器 ISR 调用，禁止忙等） */
void led_chaser_tick(void) {
    g_tick_ms += LED_TICK_MS;
    switch (g_mode) {
        case LED_MODE_CHASE:
            g_pos = (uint8_t)((g_pos + 1U) % LED_COUNT);
            break;
        case LED_MODE_BOUNCE:
            if (g_dir != 0U) {
                if (g_pos < (LED_COUNT - 1U)) {
                    g_pos++;
                } else {
                    g_pos--;
                    g_dir = 0U;
                }
            } else {
                if (g_pos > 0U) {
                    g_pos--;
                } else {
                    g_pos++;
                    g_dir = 1U;
                }
            }
            break;
        case LED_MODE_BLINK_ALL:
            g_pos ^= 1U;
            break;
        case LED_MODE_BREATHE:
            g_pos = (uint8_t)((g_pos + 1U) % LED_COUNT);  /* 参考：推进相位 */
            break;
        default:
            break;
    }
    /* 驱动输出（目标侧：GPIOA->ODR = mask; 宿主侧：写桩数组） */
    g_gpio_out[0] = led_chaser_current_mask();
}

/** 按钮采样 + 消抖（Req-002 / Req-004）；主循环调用，非 ISR */
void led_chaser_handle_button(void) {
    static uint8_t debounce_cnt = 0U;
    static uint8_t switched = 0U;
    if (gpio_read(1U, 0U) == 0U) {           /* PB0 active-low */
        if (debounce_cnt < LED_DEBOUNCE_MS) {
            debounce_cnt++;
        }
        if (debounce_cnt >= LED_DEBOUNCE_MS && switched == 0U) {
            led_chaser_set_mode((led_mode_t)((g_mode + 1U) % LED_MODE_COUNT));
            switched = 1U;                    /* 防连跳（单次按下只切一次） */
        }
    } else {
        debounce_cnt = 0U;
        switched = 0U;
    }
}

/* ------------------------------------------------------------------ */
/* 入口（宿主单测时由 LED_CHASER_UNIT_TEST 屏蔽，避免与 test runner 重定义 main） */
/* ------------------------------------------------------------------ */
#ifndef LED_CHASER_UNIT_TEST
int main(void) {
    led_chaser_init();
    for (;;) {
        led_chaser_handle_button();
        led_chaser_tick();
        /* 目标侧：__WFI();  // Req-005 空闲睡眠，唤醒源 TIM2/SysTick/EXTI
         * 宿主侧：无中断，循环即占位。 */
    }
}
#endif
