/*
 * STM32 HAL Application
 */

#include "main.h"
#include "FreeRTOS.h"
#include "task.h"

static void vLEDTask(void *pvParameters)
{
    (void)pvParameters;
    for (;;) {
        HAL_GPIO_TogglePin(LD2_GPIO_Port, LD2_Pin);
        vTaskDelay(pdMS_TO_TICKS(500));
    }
}

int main(void)
{
    HAL_Init();
    SystemClock_Config();
    MX_GPIO_Init();
    MX_USART2_UART_Init();
    xTaskCreate(vLEDTask, "LED", configMINIMAL_STACK_SIZE, NULL, tskIDLE_PRIORITY + 1, NULL);
    vTaskStartScheduler();
    while (1) {}
}

void SystemClock_Config(void)
{
    /* STM32F4: HSE 8MHz -> PLL -> 168MHz SYSCLK */
}

void Error_Handler(void) { while (1) {} }
