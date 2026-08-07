/*
 * MISRA Benchmark — Case 005: False Positive Risk
 * Rule: MISRA C:2023 Rule 11.1 — pointer conversion to/from integral types
 *
 * CMSIS/HAL register access pattern — very common in embedded C.
 * Casting integer literal to a pointer is required for hardware register access.
 *
 * Expected: cppcheck false positive
 */
#include <stdint.h>

/* STM32 USART register (common HAL pattern) */
/* cppcheck-suppress [misra-c2023-11.1, misra-c2023-11.3] — HAL macro pattern */
#define USART1_BASE     ((uint32_t)0x40011000U)
/* cppcheck-suppress [misra-c2023-11.1, misra-c2023-11.3] — HAL macro pattern */
#define USART1_DR       (*(volatile uint32_t *)(USART1_BASE + 0x04U))
/* cppcheck-suppress [misra-c2023-11.1, misra-c2023-11.3] — HAL macro pattern */
#define USART1_SR       (*(volatile uint32_t *)(USART1_BASE + 0x00U))

void uart_send_char(char c) {
    /* Wait for TX empty flag */
    while (!(USART1_SR & 0x80U)) {
        /* spin */
    }
    USART1_DR = (uint32_t)c;
}
