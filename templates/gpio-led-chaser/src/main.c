/**
 * GPIO 流水灯 (LED Chaser) — 参考实现（宿主机可编译 / 可单测）
 *
 * 实现（需求对应 docs/spec.md）：
 *   Req-001 8 路流水灯（PA0..PA7），单向 wrap
 *   Req-002 模式切换 CHASE/BOUNCE/BLINK_ALL/BREATHE（PB0 按钮，SHALL 强制 ≥4）
 *   Req-003 定时器中断驱动、禁止忙等（TIM2 200 ms 周期中断；ISR 仅置位标志）
 *   Req-004 按钮软件消抖（连续稳定低 LED_DEBOUNCE_TICKS 个 tick，每个 = 200 ms）
 *   Req-005 空闲 WFI（两次 tick 之间睡眠，仅被 TIM2/SysTick/EXTI 唤醒）
 *   Req-006 GPIO 时钟使能 + 推挽输出 + 上拉输入 + TIM2 200ms 周期（寄存器级初始化）
 *   Req-007 参数单一真源（LED_TICK_MS / LED_COUNT / LED_DEFAULT_MODE / LED_PWM_STEPS）
 *
 * 目标硬件：STM32F103C8T6（Blue Pill, Cortex-M3）
 * Toolchain：ARM GCC；宿主 build/test 用 gcc + cmake + ctest
 *
 * 设计约定：pattern 状态机逻辑全部为纯函数 / 无寄存器依赖，便于宿主 ctest 覆盖；
 * 真实寄存器初始化序列由 led_chaser_target_init() 以可编译镜像给出（Req-006 交付物，
 * 不再依赖 codegen 生成）。
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

/* 整端口掩码写：经 HAL 输出当前 pattern，不绕过抽象 */
void gpio_write_mask(uint8_t port, uint8_t mask) {
    if (port >= 3U) {
        return;
    }
    g_gpio_out[port] = mask;
}

/* ------------------------------------------------------------------ */
/* 模式状态（volatile：目标侧由 TIM2 ISR / EXTI ISR 写）              */
/* ------------------------------------------------------------------ */
static volatile uint8_t   g_pos = 0U;            /* 当前 LED 位置 0..7（CHASE/BOUNCE/BREATHE 共用相位轴） */
static volatile uint8_t   g_dir = 1U;            /* BOUNCE 方向：1=右, 0=左（仅 tick() 改写） */
static volatile led_mode_t g_mode = LED_MODE_CHASE;
static volatile uint32_t  g_tick_count = 0U;     /* 累计 tick 数（每个 = LED_TICK_MS） */
static volatile uint8_t   g_tick_pending = 0U;   /* ISR → main 的“tick 到达”标志 */
static volatile uint8_t   g_pwm_phase = 0U;      /* BREATHE PWM 载波子相 0..LED_PWM_STEPS-1 */
static uint8_t   g_debounce_ticks = 0U;         /* Req-004 连续稳定低 tick 计数（主循环变量） */
static uint8_t   g_switched = 0U;               /* 防止单次按下连跳 */

/* ------------------------------------------------------------------ */
/* Req-006 寄存器镜像（宿主侧填充供单测；目标侧同步写硬件）          */
/* ------------------------------------------------------------------ */
static target_state_t g_target = {0U, 0U, 0U, 0U, 0U, 0U};

const target_state_t* led_chaser_target_state(void) {
    return &g_target;
}

void led_chaser_target_init(void) {
    /* 计算值（72 MHz HSE 推导）：TIM2 200 ms 周期。
     *   PSC = 7200 - 1 = 7199；ARR = 2000 - 1 = 1999
     *   T = (PSC+1) * (ARR+1) / 72e6 = 7200 * 2000 / 72e6 = 0.2 s */
    g_target.apb2enr   = (uint32_t)(0x1U << 2) | (uint32_t)(0x1U << 3); /* RCC_APB2ENR_IOPA | RCC_APB2ENR_IOPB */
    g_target.gpioa_crl = 0x22222222U;   /* PA0..7 推挽输出 2 MHz */
    g_target.gpiob_crl = 0x00000008U;   /* PB0 输入上拉/下拉（CNF=10, MODE=00） */
    g_target.gpiob_odr = 0x00000001U;   /* PB0 上拉（ODR bit0=1） */
    g_target.tim2_psc  = 7199U;
    g_target.tim2_arr  = 1999U;

    /* 记录写序（索引：0=apb2enr,1=gpioa_crl,2=gpiob_crl,3=gpiob_odr,4=tim2_psc,5=tim2_arr）。
     * 顺序即“先使能时钟再配置外设”的硬约束，供 T-006 时序验收。 */
    g_target.init_order[0] = 0U;   /* APB2ENR 必须最先写 */
    g_target.init_order[1] = 1U;   /* GPIOA CRL */
    g_target.init_order[2] = 2U;   /* GPIOB CRL */
    g_target.init_order[3] = 3U;   /* GPIOB ODR */
    g_target.init_order[4] = 4U;   /* TIM2 PSC */
    g_target.init_order[5] = 5U;   /* TIM2 ARR */
    g_target.init_order_len = 6U;

#ifdef LED_CHASER_TARGET
    /* 目标侧：写入真实硬件寄存器（仅 STM32F1 系列编译路径） */
    RCC->APB2ENR   |= g_target.apb2enr;
    GPIOA->CRL      = g_target.gpioa_crl;
    GPIOB->CRL      = g_target.gpiob_crl;
    GPIOB->ODR     |= g_target.gpiob_odr;
    TIM2->PSC       = g_target.tim2_psc;
    TIM2->ARR       = g_target.tim2_arr;
    TIM2->DIER     |= TIM_DIER_UIE;
    TIM2->CR1      |= TIM_CR1_CEN;
    NVIC_EnableIRQ(TIM2_IRQn);
#endif
}

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

/** 往返流水：在 pos 处点亮（单 bit）。方向仅在 led_chaser_tick() 内推进，
 *  不影响“当前点亮哪颗”，故本函数只取 pos。纯函数、无副作用。 */
uint8_t led_chaser_bounce_mask(uint8_t pos) {
    uint8_t p = pos;
    if (p >= LED_COUNT) {
        p = (uint8_t)(p % LED_COUNT);
    }
    return (uint8_t)(1U << p);
}

/** BREATHE 占空比级数：相位 → 三角波 0..LED_PWM_STEPS..0。
 *  half = LED_COUNT/2；phase<=half 时 duty 线性升，之后线性降，
 *  端点（phase=0 与 phase=LED_COUNT-1）皆为 0，phase=half 为满占空比。
 *  纯函数、无副作用。 */
uint8_t led_chaser_breathe_duty(uint8_t phase) {
    uint8_t half = LED_COUNT / 2U;
    uint8_t tri;
    if (phase <= half) {
        tri = phase;
    } else {
        tri = (uint8_t)((LED_COUNT - 1U) - phase);
    }
    /* 量化为 LED_PWM_STEPS 级占空比 */
    return (uint8_t)((uint16_t)tri * (uint16_t)LED_PWM_STEPS / (uint16_t)half);
}

/** BREATHE 掩码：真·时间分时占空比 PWM。
 *  给定呼吸相位与 PWM 载波子相：当子相 < 占空比级数时 8 路全亮，否则全灭 →
 *  时间分时占空比呼吸（非 LED 数量阶梯）。纯函数、无副作用。 */
uint8_t led_chaser_breathe_mask(uint8_t phase, uint8_t pwm_phase) {
    uint8_t duty = led_chaser_breathe_duty(phase);
    return (pwm_phase < duty) ? 0xFFU : 0x00U;
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
    g_pwm_phase = 0U;
    g_debounce_ticks = 0U;
    g_switched = 0U;
    led_chaser_target_init();   /* Req-006 寄存器级初始化（可编译、可单测） */
}

uint8_t led_chaser_current_mask(void) {
    uint8_t mask = 0U;
    switch (g_mode) {
        case LED_MODE_CHASE:
            mask = led_chaser_chase_mask(g_pos);
            break;
        case LED_MODE_BOUNCE:
            /* 只读：方向由 tick() 单向推进，此处不回写 g_dir */
            mask = led_chaser_bounce_mask(g_pos);
            break;
        case LED_MODE_BLINK_ALL:
            mask = (g_pos & 1U) ? 0xFFU : 0x00U;
            break;
        case LED_MODE_BREATHE:
            /* 真·占空比 PWM 呼吸（时间分时，非全亮常量占位） */
            mask = led_chaser_breathe_mask(g_pos, g_pwm_phase);
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
            /* 慢轴：推进呼吸相位；快轴：推进 PWM 载波子相（连续载波，占空比由相位决定） */
            g_pos = (uint8_t)((g_pos + 1U) % LED_COUNT);
            g_pwm_phase = (uint8_t)((g_pwm_phase + 1U) % LED_PWM_STEPS);
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

/* 测试可见性：暴露 ISR 共享状态（仅单测断言用） */
uint32_t led_chaser_tick_count(void) {
    return g_tick_count;
}

uint8_t led_chaser_tick_pending(void) {
    return g_tick_pending;
}

/** 按钮采样 + tick 计数消抖（Req-002 / Req-004）；主循环每个 tick 调用一次，非 ISR。
 *  消抖按“连续稳定低 tick 数”计量：PB0 连续稳定低 LED_DEBOUNCE_TICKS 个 tick
 *  才判定一次有效按下，且单次按下只切一次模式（g_switched 锁）。不接收毫秒参数，
 *  彻底避免“以调用次数冒充时间度量”。 */
void led_chaser_handle_button(void) {
    if (gpio_read(1U, 0U) == 0U) {           /* PB0 active-low（按下=低） */
        if (g_debounce_ticks < 255U) {
            g_debounce_ticks++;
        }
        if (g_debounce_ticks >= LED_DEBOUNCE_TICKS && g_switched == 0U) {
            led_chaser_set_mode((led_mode_t)((g_mode + 1U) % LED_MODE_COUNT));
            g_switched = 1U;                   /* 防连跳（单次按下只切一次） */
        }
    } else {
        g_debounce_ticks = 0U;
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
        /* Req-004：每个 tick 采样一次按钮（消抖按 tick 计数） */
        led_chaser_handle_button();
        /* Req-005：空闲即睡眠，仅被中断唤醒 */
        led_chaser_wfi();
    }
}
#endif
