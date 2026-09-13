/**
 * GPIO 流水灯 (LED Chaser) — Public API
 *
 * 参考实现头文件。目标相关寄存器操作在 src/main.c 中以注释标明；
 * 宿主机（gcc + ctest）用 g_gpio_out/g_gpio_in 桩数组模拟端口。
 *
 * MISRA-C:2012 注意点：
 *   - 仅用确定性类型（uint8_t / uint32_t）。
 *   - 状态机共享变量用 volatile 标记（目标侧 ISR 写入，见下方 g_tick_*）。
 *   - 纯函数（*_mask）无副作用，方向状态仅由 led_chaser_tick() 单向推进。
 *   - 无隐式 int、无 unbounded loop、无 goto。
 */

#ifndef LED_CHASER_H
#define LED_CHASER_H

#include <stdint.h>

/* ---- 可配置参数（Req-007：单一真源） ---- */
#define LED_TICK_MS       200U   /* Req-003 step period（200 ms，TIM2 周期中断） */
#define LED_DEBOUNCE_MS   50U    /* Req-004 software debounce（稳定低 ≥ 50 ms） */
#define LED_COUNT         8U     /* PA0..PA7 */
#define LED_DEFAULT_MODE  0U     /* 0=CHASE */
/* 定时器选型（Req-003 / Req-005，单一裁决，见 spec.md §1 Req-003）：
 * 采用 TIM2 产生 200 ms 周期中断驱动 pattern step。
 * SysTick@1kHz 被显式否决：每 1 ms 唤醒一次会抵消 Req-005 的低功耗收益；
 * 若改用 SysTick 须预分频到 200 ms。 */
#define LED_TIMER_PERIOD_MS  LED_TICK_MS

/* ---- 运行模式（Req-002，SHALL 强制 ≥4，含 BREATHE） ---- */
typedef enum {
    LED_MODE_CHASE = 0,     /* 单向流水 */
    LED_MODE_BOUNCE,         /* 往返流水 */
    LED_MODE_BLINK_ALL,      /* 同步闪烁 */
    LED_MODE_BREATHE,        /* PWM 呼吸（参考实现：软件 PWM 三角波阶梯亮度） */
    LED_MODE_COUNT
} led_mode_t;

/* ---- 生命周期 / 控制 ---- */
void led_chaser_init(void);
void led_chaser_tick(void);                 /* 推进一个 step（Req-003，由定时器 ISR 调用，禁止忙等） */
void led_chaser_set_mode(led_mode_t m);
led_mode_t led_chaser_get_mode(void);
uint8_t led_chaser_current_mask(void);      /* PA0..PA7 当前输出位掩码（只读，无副作用） */

/* ---- 按钮（Req-002 / Req-004）；主循环调用，非 ISR ---- */
/* elapsed_ms：距上一次调用的经过毫秒（由 200 ms tick 时钟驱动，使 50 ms 消抖
 * 以时间计量而非“调用次数”，满足 Req-004 稳定低 ≥ 50 ms） */
void led_chaser_handle_button(uint32_t elapsed_ms);

/* ---- 定时器 ISR 钩子（Req-003）：200 ms 周期中断里调用 ---- */
void led_chaser_on_timer_isr(void);   /* 置位 tick 标志 + 累加 tick 计数（ISR 最小职责） */
void led_chaser_wfi(void);            /* Req-005：空闲 WFI 占位（宿主侧空操作，目标侧 __WFI()） */

/* ---- 纯函数（宿主可单测，Req NFR-确定性） ---- */
uint8_t led_chaser_chase_mask(uint8_t pos);
/* BOUNCE 掩码：给定位置 pos 与方向 dir(0=左 / 1=右) 的当前点亮位掩码。
 * 纯函数、无副作用；方向仅在 led_chaser_tick() 内单向推进。 */
uint8_t led_chaser_bounce_mask(uint8_t pos, uint8_t dir);
/* BREATHE 掩码：相位 phase(0..LED_COUNT-1) → 三角波亮度阶梯掩码（软件 PWM 呼吸）。
 * 亮度 lvl = phase<=LED_COUNT/2 ? phase : LED_COUNT-phase；低位 lvl 个 LED 点亮。
 * 纯函数、无副作用。 */
uint8_t led_chaser_breathe_mask(uint8_t phase);

/* ---- HAL 桩（目标侧替换为 RCC/GPIO 寄存器写） ---- */
void gpio_write(uint8_t port, uint8_t pin, uint8_t val);
uint8_t gpio_read(uint8_t port, uint8_t pin);
void gpio_write_mask(uint8_t port, uint8_t mask);   /* 整端口掩码写（经 HAL，不绕过） */
extern uint8_t g_gpio_out[3];   /* port A=0, B=1, C=2（宿主模拟） */
extern uint8_t g_gpio_in[3];

#endif /* LED_CHASER_H */
