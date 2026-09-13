/*
 * STM32 HAL 中断向量表样例（脱敏 stand-in）。BSD-3-Clause。
 * 覆盖：中断向量表数组（数组初始化器引用本文件函数 → 向量表式 ISR 命中）、
 *       HAL_UART_IRQHandler 回调、命名启发式 *_IRQHandler ISR。
 */
#include "stm32f4xx_hal.h"
#include "main.h"

extern void TIM2_IRQHandler(void);

/* 中断向量表：初始化器引用本文件 ISR 函数（向量表式 ISR 识别） */
void (* const g_pfnVectors[])(void) __attribute__((section(".isr_vector"))) = {
    (void (*)(void))0x20000000,   /* 主栈顶 */
    Reset_Handler,
    NMI_Handler,
    HardFault_Handler,
    TIM2_IRQHandler,
    USART1_IRQHandler,
};

/* Cortex-M 默认异常（命名启发式） */
void NMI_Handler(void)        { while (1) {} }
void HardFault_Handler(void)  { while (1) {} }
void Reset_Handler(void)
{
    SystemInit();
    main();
}

/* UART ISR（命名启发式 + 调用 HAL 回调） */
void USART1_IRQHandler(void)
{
    HAL_UART_IRQHandler(&huart1);
}

/* 业务：UART 接收完成回调（HAL 注册式，潜在调用候选） */
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART1) {
        HAL_UART_Receive_IT(huart, &g_rx_byte, 1);
    }
}

volatile uint8_t g_rx_byte = 0;
