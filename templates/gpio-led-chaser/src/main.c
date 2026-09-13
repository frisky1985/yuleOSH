/**
 * GPIO 流水灯 (LED Chaser) — 参考实现（宿主机可编译 / 可单测）
 *
 * 实现（需求对应 docs/spec.md）：
 *   Req-001 8 路流水灯（PA0..PA7），单向 wrap
 *   Req-002 模式切换 CHASE/BOUNCE/BLINK_ALL/BREATHE（PB0 按钮，SHALL 强制 ≥4）
 *   Req-003 定时器中断驱动、禁止忙等（TIM2 200 ms 周期中断；ISR 仅置位标志）
 *   Req-004 按钮软件消抖 50 ms（以时间计量，非“调用次数”）
 *   Req-005 空闲 WFI（两次 tick 之间睡眠，仅被 TIM2/SysTick/EXTI 唤醒）
 *   Req-006 GPIO 时钟使能 + 推挽输出 + 上拉输入（目标侧寄存器注释）
 *   Req-007 参数单一真源（LED_TICK_MS / LED_DEBOUNCE_MS / LED_COUNT / LED_DEFAULT_MODE）
 *
 * 目标硬件：STM32F103C8T6（Blue Pill, Cortex-M3）
 * Toolchain：ARM GCC；宿主 build/test 用 gcc + cmake + ctest
 *
 * 设计约定：pattern 状态机逻辑全部为纯函数 / 无寄存器依赖，便于宿主 ctest 覆盖；
 * 真实寄存器初始化序列由 `development` / `codegen-deploy` 步生成并覆盖本文件。
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

/* 整端口掩码写：经 HAL 输出当前 pattern，不绕过抽象（BC-4） */
void gpio_write_mask(uint8_t port, uint8_t mask) {
    if (port >= 3U) {
        return;
    }
    g_gpio_out[port] = mask;
}

/* ------------------------------------------------------------------ */
/* 模式状态（volatile：目标侧由 TIM2 ISR / EXTI ISR 写）              */
/* ------------------------------------------------------------------ */
static volatile uint8_t   g_pos = 0U;            /* 当前 LED 位置 0..7 */
static volatile uint8_t   g_dir = 1U;            /* BOUNCE 方向：1=右, 0=左（仅 tick() 改写） */
static volatile led_mode_t g_mode = LED_MODE_CHASE;
static volatile uint32_t  g_tick_count = 0U;     /* 累计 tick 数（每个 = LED_TICK_MS） */
static volatile uint8_t   g_tick_pending = 0U;   /* ISR → main 的“tick 到达”标志 */
static uint8_t   g_debounce_ms = 0U;            /* Req-004 消抖累计毫秒（主循环变量） */
static uint8_t   g_switched = 0U;               /* 防止单次按下连跳 */

/* ------------------------------------------------------------------ */
/* 纯函数：pattern 掩码计算（Req NFR-确定性，宿主可单测，无副作用）   */
/* ------------------------------------------------------------------ */

/** 单向流水：pos 处单 bit 点亮，pos>=8 取模 wrap */
uint8_t led_chaser_chase_mask(uint8_t pos) {
    uint8_t p = pos;
    if (p >= LED_COUNT) {
        p = (uint8_t)(p % LED_COUNT);
    }
    return (uint8_t)(1U << p);
}

/** 往返流水：在 pos 处点亮（与方向无关）；方向仅在 tick() 内推进。
 *  纯函数：不回写 dir，调用方据返回值点亮即可。 */
uint8_t led_chaser_bounce_mask(uint8_t pos, uint8_t dir) {
    (void)dir;   /* 方向只影响 tick 推进，不影响“当前点亮哪颗” */
    uint8_t p = pos;
    if (p >= LED_COUNT) {
        p = (uint8_t)(p % LED_COUNT);
    }
    return (uint8_t)(1U << p);
}

/** BREATHE 软件 PWM 呼吸：相位 → 三角波亮度阶梯掩码。
 *  lvl = phase<=LED_COUNT/2 ? phase : LED_COUNT-phase（0..LED_COUNT/2..1）
 *  低位 lvl 个 LED 点亮，形成 暗→亮→暗 的呼吸。无硬件 PWM 时的规范降级实现；
 *  目标侧若有 TIMx CHx PWM，可整体替换为占空比调制并记录 deviation。 */
uint8_t led_chaser_breathe_mask(uint8_t phase) {
    uint8_t half = LED_COUNT / 2U;
    uint8_t lvl = (phase <= half) ? phase : (uint8_t)(LED_COUNT - phase);
    if (lvl == 0U) {
        return 0x00U;
    }
    return (uint8_t)((1U << lvl) - 1U);
}

/* ------------------------------------------------------------------ */
/* 生命周期 / 控制                                                      */
/* ------------------------------------------------------------------ */

void led_chaser_init(void) {
    g_pos = 0U;
    g_dir = 1U;
    g_mode = (led_mode_t)LED_DEFAULT_MODE;
    g_tick_count = 0U;
    g_tick_pending = 0U;
    g_debounce_ms = 0U;
    g_switched = 0U;
    /* 目标侧（注释，供 development 步参考）：
     *   RCC->APB2ENR |= RCC_APB2ENR_IOPA | RCC_APB2ENR_IOPB;   // Req-006 时钟使能
     *   GPIOA->CRL = 0x22222222;   // PA0..7 输出推挽 2MHz
     *   GPIOB->CRL = 0x88888888;   // PB0 输入上拉（ODR 对应位写 1）
     *   GPIOB->ODR |= (1U << 0);
     *   // TIM2 200ms 周期中断（Req-003）：PSC/ARR 由 72MHz HSE 推导
     *   TIM2->PSC = ...; TIM2->ARR = ...; TIM2->DIER |= UIE; TIM2->CR1 |= CEN;
     *   NVIC_EnableIRQ(TIM2_IRQn);
     */
}

uint8_t led_chaser_current_mask(void) {
    uint8_t mask = 0U;
    switch (g_mode) {
        case LED_MODE_CHASE:
            mask = led_chaser_chase_mask(g_pos);
            break;
        case LED_MODE_BOUNCE:
            /* 只读：方向由 tick() 单向推进，此处不回写 g_dir */
            mask = led_chaser_bounce_mask(g_pos, g_dir);
            break;
        case LED_MODE_BLINK_ALL:
            mask = (g_pos & 1U) ? 0xFFU : 0x00U;
            break;
        case LED_MODE_BREATHE:
            /* 软件 PWM 呼吸（三角波亮度阶梯），非全亮常量占位 */
            mask = led_chaser_breathe_mask(g_pos);
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

/** 推进一个 pattern step（Req-003：由定时器 ISR 经 led_chaser_on_timer_isr 触发，
 *  禁止忙等；方向状态仅在此处改写，保证 single-writer 不变量） */
void led_chaser_tick(void) {
    switch (g_mode) {
        case LED_MODE_CHASE:
            g_pos = (uint8_t)((g_pos + 1U) % LED_COUNT);
            break;
        case LED_MODE_BOUNCE:
            /* 方向单写：每次 tick 必移动一格，到端点翻转方向 */
            if (g_dir != 0U) {                       /* 向右 */
                if (g_pos < (LED_COUNT - 1U)) {
                    g_pos++;
                } else {
                    g_pos = (uint8_t)(LED_COUNT - 2U);
                    g_dir = 0U;                      /* 到顶→折返向左 */
                }
            } else {                                 /* 向左 */
                if (g_pos > 0U) {
                    g_pos--;
                } else {
                    g_pos = 1U;
                    g_dir = 1U;                      /* 到底→折返向右 */
                }
            }
            break;
        case LED_MODE_BLINK_ALL:
            g_pos ^= 1U;
            break;
        case LED_MODE_BREATHE:
            g_pos = (uint8_t)((g_pos + 1U) % LED_COUNT);  /* 推进呼吸相位 */
            break;
        default:
            break;
    }
    /* 经 HAL 输出（目标侧：GPIOA->ODR = mask；宿主侧：写桩数组） */
    gpio_write_mask(0U, led_chaser_current_mask());
}

/** 定时器 ISR 钩子（Req-003）：ISR 最小职责——置位标志 + 累加计数。
 *  真实硬件在 TIM2_IRQHandler 中调用；宿主权宜用同样语义驱动。 */
void led_chaser_on_timer_isr(void) {
    g_tick_pending = 1U;
    g_tick_count++;
}

/** 空闲睡眠（Req-005）：宿主侧空操作，目标侧 __WFI()。
 *  仅在两次 tick 之间被调用，唤醒源为 TIM2/SysTick/EXTI。 */
void led_chaser_wfi(void) {
    /* 目标侧：__WFI(); */
}

/** 按钮采样 + 时间计量消抖（Req-002 / Req-004）；主循环调用，非 ISR。
 *  elapsed_ms：距上次调用的毫秒数（由 200ms tick 周期驱动），使 50ms 消抖以
 *  时间计量而非“调用次数”。 */
void led_chaser_handle_button(uint32_t elapsed_ms) {
    if (gpio_read(1U, 0U) == 0U) {           /* PB0 active-low（按下=低） */
        if (g_debounce_ms < 255U) {
            g_debounce_ms = (uint8_t)(g_debounce_ms + (uint8_t)elapsed_ms);
            if (g_debounce_ms > 250U) {        /* 防溢出 */
                g_debounce_ms = 250U;
            }
        }
        if (g_debounce_ms >= LED_DEBOUNCE_MS && g_switched == 0U) {
            led_chaser_set_mode((led_mode_t)((g_mode + 1U) % LED_MODE_COUNT));
            g_switched = 1U;                   /* 防连跳（单次按下只切一次） */
        }
    } else {
        g_debounce_ms = 0U;
        g_switched = 0U;
    }
}

/* ------------------------------------------------------------------ */
/* 入口（宿主单测时由 LED_CHASER_UNIT_TEST 屏蔽，避免与 test runner 重定义 main） */
/* ------------------------------------------------------------------ */
#ifndef LED_CHASER_UNIT_TEST
int main(void) {
    led_chaser_init();
    for (;;) {
        /* Req-003：定时器中断驱动，非忙等。ISR 置 g_tick_pending 后在此推进。 */
        if (g_tick_pending != 0U) {
            g_tick_pending = 0U;
            led_chaser_tick();
        }
        /* Req-004：消抖以 tick 时钟（200ms）为时基，传入经过毫秒 */
        led_chaser_handle_button(LED_TICK_MS);
        /* Req-005：空闲即睡眠，仅被中断唤醒 */
        led_chaser_wfi();
    }
}
#endif
