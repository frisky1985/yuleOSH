/**
 * @file test_hal_mock_unity.c
 * @brief Unity-based unit tests for HAL Mock implementation.
 *
 * Compile (with coverage):
 *   gcc -I../../src/yuleosh/cross -I../../src/yuleosh/cross/hal_mock
 *       --coverage -g -O0 -o test_hal_mock_unity
 *       test_hal_mock_unity.c src/unity.c
 *       ../../src/yuleosh/cross/hal_mock/hal_mock_impl.c
 *
 * License: MIT
 */

#include "unity.h"
#include "hal_mock/mock_core.h"
#include "hal_mock/uart_mock.h"
#include "hal_mock/gpio_mock.h"
#include "hal_mock/timer_mock.h"
#include "hal_mock/i2c_mock.h"
#include "hal_mock/spi_mock.h"

#include <string.h>

/* ------------------------------------------------------------------ */
/*  setUp / tearDown                                                   */
/* ------------------------------------------------------------------ */

void setUp(void) {
    mock_reset_all();
}

void tearDown(void) {
    /* nothing */
}

/* ------------------------------------------------------------------ */
/*  mock_core.h tests                                                  */
/* ------------------------------------------------------------------ */

static void test_mock_reset_all_clears_count(void) {
    /* touch a few mocks to push count */
    UART_HandleTypeDef huart;
    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);
    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);
    TEST_ASSERT_TRUE(_mock_call_count > 0);

    mock_reset_all();
    TEST_ASSERT_EQUAL_UINT(0, _mock_call_count);
}

static void test_mock_assert_call_count_exact(void) {
    UART_HandleTypeDef huart;
    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);
    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);

    TEST_ASSERT_EQUAL(0, mock_assert_call_count("HAL_UART_Transmit", 2));
}

static void test_mock_assert_call_count_wrong(void) {
    UART_HandleTypeDef huart;
    HAL_UART_Transmit(&huart, (const uint8_t*)"x", 1, 10);

    /* Returns non-zero when count doesn't match */
    TEST_ASSERT_TRUE(0 != mock_assert_call_count("HAL_UART_Transmit", 999));
}

static void test_mock_call_log_content(void) {
    mock_reset_all();
    UART_HandleTypeDef huart;
    const char *msg = "HELLO";
    HAL_UART_Transmit(&huart, (const uint8_t*)msg, 5, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_UART_Transmit", _mock_call_log[0].name);
}

/* ------------------------------------------------------------------ */
/*  UART mock tests                                                    */
/* ------------------------------------------------------------------ */

static void test_uart_transmit_records(void) {
    UART_HandleTypeDef huart;
    uint8_t data[] = "HelloUART";
    HAL_UART_Transmit(&huart, data, 10, 50);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_UART_Transmit", _mock_call_log[0].name);
    /* Verify args contain Size=10 */
    TEST_ASSERT_NOT_NULL(strstr(_mock_call_log[0].args, "Size=10"));
}

static void test_uart_receive_records(void) {
    UART_HandleTypeDef huart;
    uint8_t buf[16] = {0};
    HAL_UART_Receive(&huart, buf, 8, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_UART_Receive", _mock_call_log[0].name);
}

/* ------------------------------------------------------------------ */
/*  GPIO mock tests                                                    */
/* ------------------------------------------------------------------ */

static void test_gpio_write_pin_set(void) {
    GPIO_TypeDef gpio;
    /* Pin mask 0x01 = bit 0, writes to _mock_gpio_pins[0] */
    HAL_GPIO_WritePin(&gpio, 0x01, GPIO_PIN_SET);
    TEST_ASSERT_TRUE(_mock_gpio_pins[0] & 0x01);
}

static void test_gpio_write_pin_reset(void) {
    GPIO_TypeDef gpio;
    /* Pin mask 0x02 = bit 1, writes to _mock_gpio_pins[1] */
    _mock_gpio_pins[1] = 1; /* pre-set high */
    HAL_GPIO_WritePin(&gpio, 0x02, GPIO_PIN_RESET);
    TEST_ASSERT_TRUE(!(_mock_gpio_pins[1]));
}

static void test_gpio_read_pin(void) {
    GPIO_TypeDef gpio;
    /* Pin mask 0x04 = bit 2, reads from _mock_gpio_pins[2] */
    _mock_gpio_pins[2] = 1;
    GPIO_PinState val = HAL_GPIO_ReadPin(&gpio, 0x04);
    TEST_ASSERT_EQUAL(GPIO_PIN_SET, val);
}

static void test_gpio_toggle_pin(void) {
    GPIO_TypeDef gpio;
    /* Pin mask 0x08 = bit 3, which toggles _mock_gpio_pins[3] */
    _mock_gpio_pins[3] = 0x00;
    HAL_GPIO_TogglePin(&gpio, 0x08);
    TEST_ASSERT_EQUAL_UINT(0x01, _mock_gpio_pins[3]);
    HAL_GPIO_TogglePin(&gpio, 0x08);
    TEST_ASSERT_EQUAL_UINT(0x00, _mock_gpio_pins[3]);
}

/* ------------------------------------------------------------------ */
/*  Timer mock tests                                                   */
/* ------------------------------------------------------------------ */

static void test_timer_base_start_stop(void) {
    TIM_HandleTypeDef htim;

    _hal_tim_base_start_mock(&htim);
    TEST_ASSERT_TRUE(_mock_timer_running);

    _hal_tim_base_stop_mock(&htim);
    TEST_ASSERT_FALSE(_mock_timer_running);
}

/* ------------------------------------------------------------------ */
/*  I2C mock tests                                                     */
/* ------------------------------------------------------------------ */

static void test_i2c_master_transmit(void) {
    I2C_HandleTypeDef hi2c;
    uint8_t data[] = {0x01, 0x02, 0x03};
    HAL_I2C_Master_Transmit(&hi2c, 0x50, data, 3, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_I2C_Master_Transmit", _mock_call_log[0].name);
}

static void test_i2c_mem_read(void) {
    I2C_HandleTypeDef hi2c;
    uint8_t val[2] = {0};
    mock_i2c_set_rx_data(0x48, (const uint8_t*)"\x1A\x2B", 2);
    HAL_I2C_Mem_Read(&hi2c, 0x48, 0x00, 1, val, 2, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_I2C_Mem_Read", _mock_call_log[0].name);
    TEST_ASSERT_EQUAL(0x1A, val[0]);
    TEST_ASSERT_EQUAL(0x2B, val[1]);
}

static void test_i2c_mem_write(void) {
    I2C_HandleTypeDef hi2c;
    uint8_t data[] = {0xAA, 0xBB};
    HAL_I2C_Mem_Write(&hi2c, 0x30, 0x05, 1, data, 2, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_I2C_Mem_Write", _mock_call_log[0].name);
}

/* ------------------------------------------------------------------ */
/*  SPI mock tests                                                     */
/* ------------------------------------------------------------------ */

static void test_spi_transmit(void) {
    SPI_HandleTypeDef hspi;
    uint8_t data[] = {0xA5};
    HAL_SPI_Transmit(&hspi, data, 1, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_SPI_Transmit", _mock_call_log[0].name);
}

static void test_spi_transmit_receive(void) {
    SPI_HandleTypeDef hspi;
    uint8_t tx = 0x55;
    uint8_t rx = 0x00;
    HAL_SPI_TransmitReceive(&hspi, &tx, &rx, 1, 100);

    TEST_ASSERT_EQUAL_UINT(1, _mock_call_count);
    TEST_ASSERT_EQUAL_STRING("HAL_SPI_TransmitReceive", _mock_call_log[0].name);
}

/* ------------------------------------------------------------------ */
/*  Main — Test Runner                                                */
/* ------------------------------------------------------------------ */

int main(void) {
    UnityBegin("HAL_Mock_TestSuite");

    /* Core mock */
    RUN_TEST(test_mock_reset_all_clears_count);
    RUN_TEST(test_mock_assert_call_count_exact);
    RUN_TEST(test_mock_assert_call_count_wrong);
    RUN_TEST(test_mock_call_log_content);

    /* UART */
    RUN_TEST(test_uart_transmit_records);
    RUN_TEST(test_uart_receive_records);

    /* GPIO */
    RUN_TEST(test_gpio_write_pin_set);
    RUN_TEST(test_gpio_write_pin_reset);
    RUN_TEST(test_gpio_read_pin);
    RUN_TEST(test_gpio_toggle_pin);

    /* Timer */
    RUN_TEST(test_timer_base_start_stop);

    /* I2C */
    RUN_TEST(test_i2c_master_transmit);
    RUN_TEST(test_i2c_mem_read);
    RUN_TEST(test_i2c_mem_write);

    /* SPI */
    RUN_TEST(test_spi_transmit);
    RUN_TEST(test_spi_transmit_receive);

    return UnityEnd();
}
