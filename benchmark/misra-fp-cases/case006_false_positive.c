/*
 * MISRA Benchmark — Case 006: False Positive Risk
 * Rule: MISRA C:2023 Rule 10.7 — logical operands: != used with boolean
 *
 * In STM32 HAL, status values like HAL_OK (= 0) are compared with !=.
 * cppcheck may treat HAL_OK as uint32_t rather than boolean, then flag it.
 *
 * Expected: cppcheck false positive
 */
#include <stdint.h>

/* Simulate STM32 HAL status type */
#define HAL_OK      0x00U
#define HAL_ERROR   0x01U
#define HAL_BUSY    0x02U

uint32_t hal_uart_transmit(uint32_t usart, const uint8_t *data, uint16_t len) {
    (void)usart; (void)data; (void)len;
    return HAL_OK;
}

void send_message(void) {
    uint8_t msg[] = "Hello";
    /* HAL check pattern — widespread in embedded code */
    /* cppcheck-suppress [misra-c2023-10.7, misra-c2023-14.4] — HAL status check */
    if (hal_uart_transmit(0x40011000U, msg, 5) != HAL_OK) {
        /* Error handling */
    }
}
