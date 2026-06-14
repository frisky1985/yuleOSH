/**
 * @file    platform_stm32.c
 * @brief   STM32F4 platform abstraction for UART demo host build.
 *
 * Provides stub implementations of platform functions used by the ESP32
 * bridge code, for host-side compilation verification.
 */

#include "uart_bridge.h"
#include <stdio.h>
#include <time.h>

uint32_t platform_millis(void) {
    return (uint32_t)(clock() / (CLOCKS_PER_SEC / 1000));
}

int platform_uart_write(int uart_num, const uint8_t *data, size_t len) {
    (void)uart_num;
    return (int)fwrite(data, 1, len, stdout);
}

int platform_uart_read(int uart_num, uint8_t *buffer, size_t max_len) {
    (void)uart_num;
    (void)buffer;
    (void)max_len;
    return 0;
}

void platform_log(const char *msg) {
    if (msg) {
        fprintf(stdout, "[STM32-PLAT] %s\n", msg);
    }
}
