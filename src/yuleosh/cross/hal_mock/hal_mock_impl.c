/**
 * @file hal_mock_impl.c
 * @brief Single compilation unit with all HAL mock implementations.
 *
 * Include this .c file in your test build to get all mocks.
 * Do NOT compile separately and link — include directly.
 *
 * File-scope symbols have external linkage with matching extern
 * declarations in their respective headers (.h), satisfying MISRA
 * C:2023 Rule 8.4 (compatible declarations visible).
 *
 * Compile with:
 *   gcc -I src/cross -I src/cross/hal_mock tests/test_hal_mock.c src/cross/hal_mock/hal_mock_impl.c
 *
 * License: MIT
 */

#include "hal_mock/mock_core.h"
#include "hal_mock/uart_mock.h"
#include "hal_mock/gpio_mock.h"
#include "hal_mock/timer_mock.h"
#include "hal_mock/i2c_mock.h"
#include "hal_mock/spi_mock.h"

/* Core call log — extern declarations in mock_core.h */
MockCall _mock_call_log[256];
uint32_t _mock_call_count = 0;
uint64_t _mock_current_tick = 0;

/* UART mock state — extern declarations in uart_mock.h */
uint8_t  _mock_uart_rx_data[1024];
uint32_t _mock_uart_rx_len = 0;
uint8_t  _mock_uart_tx_data[1024];
uint32_t _mock_uart_tx_len = 0;

/* GPIO mock state — extern declarations in gpio_mock.h */
uint8_t _mock_gpio_pins[16];

/* Timer mock state — extern declarations in timer_mock.h */
uint64_t _mock_timer_ticks = 0;
bool     _mock_timer_running = false;

/* I2C mock state — extern declarations in i2c_mock.h */
uint8_t  _mock_i2c_rx_data[256];
uint32_t _mock_i2c_rx_len = 0;

/* SPI mock state — extern declarations in spi_mock.h */
uint8_t  _mock_spi_rx_data[256];
uint32_t _mock_spi_rx_len = 0;
