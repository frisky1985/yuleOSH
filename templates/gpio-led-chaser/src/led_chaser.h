/**
 * GPIO 流水灯 (LED Chaser) — Public API
 *
 * 参考实现头文件。目标相关寄存器操作在 src/main.c 中以注释标明；
 * 宿主机（gcc + ctest）用 g_gpio_out/g_gpio_in 桩数组模拟端口。
 *
 * MISRA-C:2012 注意点：
 *   - 仅用确定性类型（uint8_t / uint32_t）。
 *   - 状态机共享变量用 volatile 标记（目标侧 ISR 写入）。
 *   - 无隐式 int、无 unbounded loop、无 goto。
 */

#ifndef LED_CHASER_H
#define LED_CHASER_H

#include <stdint.h>

/* ---- 可配置参数（Req-007：单一真源） ---- */
#define LED_TICK_MS       200U   /* Req-003 step period */
#define LED_DEBOUNCE_MS   50U    /* Req-004 software debounce */
#define LED_COUNT         8U     /* PA0..PA7 */
#define LED_DEFAULT_MODE  0U     /* 0=CHASE */

/* ---- 运行模式（Req-002） ---- */
typedef enum {
    LED_MODE_CHASE = 0,     /* 单向流水 */
    LED_MODE_BOUNCE,         /* 往返流水 */
    LED_MODE_BLINK_ALL,      /* 同步闪烁 */
    LED_MODE_BREATHE,        /* PWM 呼吸（参考实现：全亮渐变占位） */
    LED_MODE_COUNT
} led_mode_t;

/* ---- 生命周期 / 控制 ---- */
void led_chaser_init(void);
void led_chaser_tick(void);                 /* 推进一个 step（Req-003） */
void led_chaser_set_mode(led_mode_t m);
led_mode_t led_chaser_get_mode(void);
uint8_t led_chaser_current_mask(void);      /* PA0..PA7 当前输出位掩码 */

/* ---- 按钮（Req-002 / Req-004） ---- */
void led_chaser_handle_button(void);

/* ---- 纯函数（宿主可单测，Req NFR-确定性） ---- */
uint8_t led_chaser_chase_mask(uint8_t pos);
uint8_t led_chaser_bounce_mask(uint8_t pos, uint8_t *p_dir);

/* ---- HAL 桩（目标侧替换为 RCC/GPIO 寄存器写） ---- */
void gpio_write(uint8_t port, uint8_t pin, uint8_t val);
uint8_t gpio_read(uint8_t port, uint8_t pin);
extern uint8_t g_gpio_out[3];   /* port A=0, B=1, C=2（宿主模拟） */
extern uint8_t g_gpio_in[3];

#endif /* LED_CHASER_H */
