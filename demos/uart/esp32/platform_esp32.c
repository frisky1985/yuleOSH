/**
 * @file    platform_esp32.c
 * @brief   ESP32 platform abstraction for UART demo host build.
 *
 * Provides stub implementations of platform functions that would normally
 * call ESP-IDF drivers. Used for host-side compilation verification.
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
    return 0;  /* no real UART hardware on host */
}

void platform_log(const char *msg) {
    if (msg) {
        fprintf(stdout, "[ESP32-PLAT] %s\n", msg);
    }
}
