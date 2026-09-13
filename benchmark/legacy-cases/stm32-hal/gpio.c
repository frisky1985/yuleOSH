/*
 * STM32 HAL 代表性样例（脱敏 stand-in，非真实 ST 仓库代码）。
 * 许可证：BSD-3-Clause（与上游 STM32Cube HAL 一致）。
 * 覆盖：HAL 初始化函数、volatile 寄存器映射全局、对象/函数宏、
 *       __attribute__((interrupt)) ISR、条件编译选系列。
 */
#include "stm32f4xx_hal.h"
#include "main.h"

/* 对象宏：寄存器基址（带值，高置信度）；整数极值宏应走白名单 */
#define GPIOA_BASE 0x40020000U
#define GPIO_PIN_5 ((uint16_t)0x0020)
#define LED_ON 1
#define LED_OFF 0

/* volatile 全局：外设句柄（HAL 惯例全局句柄） */
UART_HandleTypeDef huart1;
volatile uint32_t g_tick_count = 0;

/* HAL GPIO 初始化（函数定义） */
void MX_GPIO_Init(void)
{
    GPIO_InitTypeDef gpio = {0};
    __HAL_RCC_GPIOA_CLK_ENABLE();
    gpio.Pin = GPIO_PIN_5;
    gpio.Mode = GPIO_MODE_OUTPUT_PP;
    gpio.Pull = GPIO_NOPULL;
    gpio.Speed = GPIO_SPEED_FREQ_LOW;
    HAL_GPIO_Init((GPIO_TypeDef *)GPIOA_BASE, &gpio);
}

/* 业务函数：LED 控制（直接调用 HAL_GPIO_WritePin → call 边） */
void led_set(int on)
{
    HAL_GPIO_WritePin((GPIO_TypeDef *)GPIOA_BASE, GPIO_PIN_5,
                      on ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

/* 中断服务例程（__attribute__((interrupt)) 命中） */
__attribute__((interrupt)) void TIM2_IRQHandler(void)
{
    g_tick_count += 1;
    HAL_TIM_IRQHandler(&htim2);
}

/* 不同 STM32 系列差异（条件编译） */
#if defined(STM32F4)
static void clock_f4(void) { SystemCoreClockUpdate(); }
#elif defined(STM32L4)
static void clock_l4(void) { SystemCoreClockUpdate(); }
#else
static void clock_default(void) { SystemCoreClockUpdate(); }
#endif
