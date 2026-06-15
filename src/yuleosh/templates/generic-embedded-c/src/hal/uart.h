#ifndef HAL_UART_H
#define HAL_UART_H
#include <stdint.h>
#define UART_DEBUG 0
void hal_uart_init(uint8_t id, uint32_t baud);
void hal_uart_putc(uint8_t id, char c);
void hal_uart_puts(uint8_t id, const char *s);
char hal_uart_getc(uint8_t id);
uint8_t hal_uart_available(uint8_t id);
#endif
