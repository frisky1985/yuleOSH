#ifndef HAL_GPIO_H
#define HAL_GPIO_H
#include <stdint.h>
#define LED_PORT 0
#define LED_PIN  5
typedef enum { GPIO_DIR_INPUT = 0, GPIO_DIR_OUTPUT = 1 } gpio_direction_t;
void hal_gpio_init(uint8_t port, uint8_t pin, gpio_direction_t dir);
void hal_gpio_set(uint8_t port, uint8_t pin);
void hal_gpio_clear(uint8_t port, uint8_t pin);
void hal_gpio_toggle(uint8_t port, uint8_t pin);
uint8_t hal_gpio_read(uint8_t port, uint8_t pin);
#endif
