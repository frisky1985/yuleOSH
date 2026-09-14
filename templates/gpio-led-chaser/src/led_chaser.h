/**
 * GPIO 流水灯 (LED Chaser) — Public API
 *
 * 参考实现头文件。目标相关寄存器操作由 led_chaser_target_init() 以可编译的
 * 寄存器镜像（target_state_t）给出，宿主侧（gcc + ctest）经 g_gpio_out/g_gpio_in
 * 桩数组与 g_target 镜像模拟端口与寄存器。
 *
 * MISRA-C:2012 注意点：
 *   - 仅用确定性类型（uint8_t / uint32_t）。
 *   - 状态机共享变量用 volatile 标记（目标侧 ISR 写入，见下方 g_tick_*）。
 *   - 纯函数（*_mask / *_duty）无副作用，方向状态仅由 led_chaser_tick() 单向推进。
 *   - 无隐式 int、无 unbounded loop、无 goto。
 */

// @req Req-001, Req-002, Req-003, Req-004, Req-005, Req-006, Req-007

#ifndef LED_CHASER_H
#define LED_CHASER_H

#include <stdint.h>

/* ---- 可配置参数（Req-007：单一真源） ---- */
#define LED_TICK_MS          200U   /* Req-003 step period（200 ms，TIM2 周期中断） */
#define LED_COUNT            8U     /* PA0..PA7 */
#define LED_DEFAULT_MODE     0U     /* 0=CHASE */
#define LED_PWM_STEPS        8U     /* BREATHE PWM 载波占空比量化级数（时间分时） */
#define LED_DEBOUNCE_MS      50U    /* Req-004 名义消抖 ≥ 50 ms（按 tick 量化，见下） */
/* 消抖按“连续稳定低 tick 数”计量，每个 tick = LED_TICK_MS。
 * LED_DEBOUNCE_TICKS 由名义消抖时间向上取整到 tick 粒度：
 *   ceil(50 / 200) = 1 → 至少 1 个稳定低 tick（= 200 ms）即满足 ≥ 50 ms。
 * 取 2 留余量，覆盖机械抖动（≥ 400 ms 稳定低才判按下）。 */
#define LED_DEBOUNCE_TICKS   2U
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
    LED_MODE_BREATHE,        /* PWM 呼吸（真·占空比时间分时，参考实现） */
    LED_MODE_COUNT
} led_mode_t;

/* ---- 生命周期 / 控制 ---- */
void led_chaser_init(void);
void led_chaser_tick(void);                 /* 推进一个 step（Req-003，由定时器 ISR 调用，禁止忙等） */
void led_chaser_set_mode(led_mode_t m);
led_mode_t led_chaser_get_mode(void);
uint8_t led_chaser_current_mask(void);      /* PA0..PA7 当前输出位掩码（只读，无副作用） */

/* ---- 按钮（Req-002 / Req-004）；主循环每个 tick 调用一次，非 ISR ---- */
/* 消抖按 tick 计数（连续稳定低 LED_DEBOUNCE_TICKS 个 tick），不接收“毫秒”参数，
 * 避免以调用次数冒充时间度量。 */
void led_chaser_handle_button(void);

/* ---- 定时器 ISR 钩子（Req-003）：200 ms 周期中断里调用 ---- */
void led_chaser_on_timer_isr(void);   /* 置位 tick 标志 + 累加 tick 计数（ISR 最小职责） */
void led_chaser_wfi(void);            /* Req-005：空闲 WFI 占位（宿主侧空操作，目标侧 __WFI()） */

/* ---- 纯函数（宿主可单测，Req NFR-确定性） ---- */
uint8_t led_chaser_chase_mask(uint8_t pos);
/* BOUNCE 掩码：给定位置 pos 的当前点亮位掩码（单 bit 点亮）。
 * 纯函数、无副作用；往返方向仅在 led_chaser_tick() 内单向推进，不影响“当前点亮哪颗”，
 * 故本函数只取 pos。禁止给纯函数强加不存在的参数（如 dir）。 */
uint8_t led_chaser_bounce_mask(uint8_t pos);
/* BREATHE 占空比级数：phase(0..LED_COUNT-1) → 三角波 0..LED_PWM_STEPS..0。
 * 纯函数、无副作用。 */
uint8_t led_chaser_breathe_duty(uint8_t phase);
/* BREATHE 掩码：给定呼吸相位与 PWM 载波子相 → 8 路时间分时占空比（0xFF=亮 / 0x00=灭），
 * 真·占空比呼吸（非 LED 数量阶梯）。纯函数、无副作用。 */
uint8_t led_chaser_breathe_mask(uint8_t phase, uint8_t pwm_phase);

/* ---- Req-006：寄存器级初始化（可编译参考实现） ---- */
/* 寄存器镜像：宿主侧填充供单测断言；目标侧（LED_CHASER_TARGET 宏）同步写真实硬件。
 * init_order / init_order_len 记录寄存器写序（索引：0=apb2enr,1=gpioa_crl,2=gpiob_crl,
 * 3=gpiob_odr,4=tim2_psc,5=tim2_arr），供“先使能时钟再配置 GPIO/TIM”的时序验收。 */
typedef struct {
    uint32_t apb2enr;    /* RCC->APB2ENR  （bit2=IOPA, bit3=IOPB 时钟使能） */
    uint32_t gpioa_crl;  /* GPIOA->CRL    （PA0..7 推挽输出 2MHz = 0x22222222） */
    uint32_t gpiob_crl;  /* GPIOB->CRL    （PB0 输入上拉 = 0x00000008） */
    uint32_t gpiob_odr;  /* GPIOB->ODR    （PB0 上拉 = bit0=1） */
    uint32_t tim2_psc;   /* TIM2->PSC     （72MHz → 200ms：PSC=7199, ARR=1999） */
    uint32_t tim2_arr;   /* TIM2->ARR     （(7199+1)*(1999+1)/72e6 = 0.2s） */
    uint8_t  init_order[8];   /* 写序寄存器索引序列（见上） */
    uint8_t  init_order_len;  /* 有效长度 */
} target_state_t;
void led_chaser_target_init(void);
const target_state_t* led_chaser_target_state(void);

/* ---- 测试可见性：暴露 ISR 共享状态（仅单测断言用，非对外 API） ---- */
uint32_t led_chaser_tick_count(void);
uint8_t  led_chaser_tick_pending(void);

/* ---- HAL 桩（目标侧替换为 RCC/GPIO 寄存器写） ---- */
void gpio_write(uint8_t port, uint8_t pin, uint8_t val);
uint8_t gpio_read(uint8_t port, uint8_t pin);
void gpio_write_mask(uint8_t port, uint8_t mask);   /* 整端口掩码写（经 HAL，不绕过） */
extern uint8_t g_gpio_out[3];   /* port A=0, B=1, C=2（宿主模拟） */
extern uint8_t g_gpio_in[3];

#endif /* LED_CHASER_H */
