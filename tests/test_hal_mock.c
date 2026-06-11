/**
 * @file test_hal_mock.c
 * @brief Host-side tests for HAL Mock framework.
 *
 * Compile (single translation unit — required for ARM64 compat):
 *   gcc -I../../src/cross -I../../src/cross/hal_mock test_hal_mock.c ../../src/cross/hal_mock/hal_mock_impl.c
 *
 * Or as a standalone test from repo root:
 *   gcc -Isrc/cross -Isrc/cross/hal_mock tests/test_hal_mock.c src/cross/hal_mock/hal_mock_impl.c -o /tmp/test_hal_mock
 *   /tmp/test_hal_mock
 *
 * License: MIT
 */

#include "hal_mock/uart_mock.h"
#include "hal_mock/gpio_mock.h"
#include "hal_mock/timer_mock.h"
#include "hal_mock/i2c_mock.h"
#include "hal_mock/spi_mock.h"

#include <stdio.h>
#include <string.h>

/* ------------------------------------------------------------------ */
/*  Fake firmware functions                                           */
/* ------------------------------------------------------------------ */

static UART_HandleTypeDef huart1;
static GPIO_TypeDef       gpioa;
static I2C_HandleTypeDef  hi2c1;
static SPI_HandleTypeDef  hspi1;

static void fake_firmware_send_hello(void) {
    const char msg[] = "Hello from firmware!\r\n";
    HAL_GPIO_WritePin(&gpioa, 0x01, GPIO_PIN_SET);
    HAL_UART_Transmit(&huart1, (const uint8_t*)msg, (uint16_t)strlen(msg), 100);
    HAL_GPIO_WritePin(&gpioa, 0x01, GPIO_PIN_RESET);
}

static void fake_firmware_read_sensor(void) {
    uint8_t cmd = 0x01;
    uint8_t buf[4] = {0};
    HAL_GPIO_WritePin(&gpioa, 0x02, GPIO_PIN_SET);
    HAL_SPI_TransmitReceive(&hspi1, &cmd, buf, 4, 100);
    HAL_GPIO_WritePin(&gpioa, 0x02, GPIO_PIN_RESET);
}

static void fake_firmware_i2c_read_temp(void) {
    uint8_t reg = 0x00;
    uint8_t val[2] = {0};
    mock_i2c_set_rx_data(0x48, (const uint8_t*)"\x1A\x2B", 2);
    HAL_I2C_Mem_Read(&hi2c1, 0x48, reg, 1, val, 2, 100);
}

/* ------------------------------------------------------------------ */
/*  Tests                                                              */
/* ------------------------------------------------------------------ */

static int test_uart_gpio_sequence(void) {
    printf("  TEST: uart_gpio_sequence... ");
    mock_reset_all();

    fake_firmware_send_hello();

    if (mock_assert_call_count("HAL_UART_Transmit", 1)) return 1;
    if (mock_assert_call_count("HAL_GPIO_WritePin", 2)) return 1;

    printf("PASS\n");
    return 0;
}

static int test_spi_cs_sequence(void) {
    printf("  TEST: spi_cs_sequence... ");
    mock_reset_all();

    fake_firmware_read_sensor();

    if (mock_assert_call_count("HAL_GPIO_WritePin", 2)) return 1;
    if (mock_assert_call_count("HAL_SPI_TransmitReceive", 1)) return 1;

    printf("PASS\n");
    return 0;
}

static int test_i2c_mem_read(void) {
    printf("  TEST: i2c_mem_read... ");
    mock_reset_all();

    fake_firmware_i2c_read_temp();

    if (mock_assert_call_count("HAL_I2C_Mem_Read", 1)) return 1;

    printf("PASS\n");
    return 0;
}

static int test_all_peripherals_recorded(void) {
    printf("  TEST: all_peripherals... ");
    mock_reset_all();

    /* Touch every mock at least once */
    UART_HandleTypeDef huart;
    GPIO_TypeDef       gpio;
    TIM_HandleTypeDef  htim;
    I2C_HandleTypeDef  hi2c;
    SPI_HandleTypeDef  hspi;

    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);
    HAL_GPIO_WritePin(&gpio, 0x01, GPIO_PIN_SET);
    HAL_GPIO_ReadPin(&gpio, 0x01);
    HAL_GPIO_TogglePin(&gpio, 0x01);
    _hal_tim_base_start_mock(&htim);
    _hal_tim_base_stop_mock(&htim);
    mock_i2c_set_rx_data(0x48, (const uint8_t*)"x", 1);
    HAL_I2C_Master_Transmit(&hi2c, 0x48, (const uint8_t*)"x", 1, 10);
    HAL_I2C_Mem_Write(&hi2c, 0x48, 0x00, 1, (const uint8_t*)"x", 1, 10);
    HAL_SPI_Transmit(&hspi, (const uint8_t*)"x", 1, 10);
    HAL_SPI_TransmitReceive(&hspi, (const uint8_t*)"x", (uint8_t*)"x", 1, 10);

    /* Can't easily call HAL_UART_Receive without triggering macro expansion issues */
    /* Just verify we got at least 10 calls */
    if (_mock_call_count < 10) {
        fprintf(stderr, "[FAIL] expected >=10 mock calls, got %u\n", _mock_call_count);
        return 1;
    }
    printf("PASS (%u calls)\n", _mock_call_count);
    return 0;
}

/* ------------------------------------------------------------------ */
/*  Main                                                               */
/* ------------------------------------------------------------------ */

int main(void) {
    int failed = 0;

    printf("=== HAL Mock Tests ===\n");
    failed += test_uart_gpio_sequence();
    failed += test_spi_cs_sequence();
    failed += test_i2c_mem_read();
    failed += test_all_peripherals_recorded();
    printf("======================\n");
    printf("Results: %d / 4 passed\n", 4 - failed);

    return failed ? 1 : 0;
}
