/*
 * Generic Embedded C Application
 */

#include <stdint.h>
#include "hal/gpio.h"

int main(void)
{
    system_clock_init();
    hal_gpio_init(LED_PORT, LED_PIN, GPIO_DIR_OUTPUT);

    while (1) {
        hal_gpio_toggle(LED_PORT, LED_PIN);
        software_delay_ms(500);
    }
    return 0;
}

void system_clock_init(void) {}

void software_delay_ms(uint32_t ms)
{
    volatile uint32_t count;
    while (ms--) {
        count = 8000;
        while (count--) { __asm__ volatile ("nop"); }
    }
}
