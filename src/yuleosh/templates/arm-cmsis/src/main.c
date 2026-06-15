/*
 * ARM CMSIS Bare-Metal Application
 */

#include "CMSIS/core_cm4.h"

static volatile uint32_t system_tick = 0;

void SysTick_Handler(void) { system_tick++; }

void delay_ms(uint32_t ms)
{
    uint32_t target = system_tick + ms;
    while (system_tick < target) { __WFI(); }
}

int main(void)
{
    SystemInit();
    SysTick_Config(SystemCoreClock / 1000);
    __enable_irq();
    while (1) {
        delay_ms(500);
    }
}
