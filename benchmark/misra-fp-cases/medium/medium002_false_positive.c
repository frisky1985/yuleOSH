/*
 * MISRA Benchmark — Medium 002: False Positive
 * Rule: MISRA C:2023 Rule 11.4 — Conversions between pointer and integer types
 *
 * This code uses mem-mapped I/O registers in an embedded RTOS HAL driver.
 * uintptr_t cast is safe and well-defined, but cppcheck may flag it.
 *
 * Expected: cppcheck false positive (0 real violations)
 */
#include <stdint.h>

/* MMIO register base — common embedded pattern */
#define UART_BASE 0x40001000UL

typedef struct {
    volatile uint32_t DR;
    volatile uint32_t SR;
    volatile uint32_t CR;
} uart_reg_t;

static uart_reg_t *const uart = (uart_reg_t *)(uintptr_t)UART_BASE;

void uart_send_byte(uint8_t byte) {
    /* Wait for TX ready, then send */
    while (!(uart->SR & 0x20)) { }
    uart->DR = byte;
}
