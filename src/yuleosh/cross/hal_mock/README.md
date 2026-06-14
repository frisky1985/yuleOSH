# HAL Mock — Host-Side STM32 HAL Test Doubles

Host-compatible C mocks for STM32 HAL peripherals (UART, GPIO, Timer, I2C, SPI).
Link against these in x86_64 test builds to exercise firmware logic without target hardware.

## Usage

```c
#include "hal_mock/uart_mock.h"
#include "hal_mock/gpio_mock.h"

void test_uart_output(void) {
    mock_reset_all();

    // Call firmware function that writes to UART
    firmware_init();
    firmware_send_hello();

    // Verify the mock captured the call
    mock_assert_uart_transmit("Hello World\r\n");
    mock_assert_call_order("HAL_GPIO_WritePin", "HAL_UART_Transmit");
}
```

## Peripherals

| Module | Status | File |
|--------|--------|------|
| UART   | ✅     | `uart_mock.h` |
| GPIO   | ✅     | `gpio_mock.h` |
| Timer  | ✅     | `timer_mock.h` |
| I2C    | ✅     | `i2c_mock.h` |
| SPI    | ✅     | `spi_mock.h` |

## Building

```bash
cd yuleOSH
gcc -I src/cross -I src/cross/hal_mock test/my_firmware_test.c -o /tmp/test_fw
/tmp/test_fw
```
