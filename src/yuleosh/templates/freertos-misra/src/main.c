/*
 * FreeRTOS + MISRA Application
 */

#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

static QueueHandle_t xAppQueue = NULL;

static void vAppTask(void *pvParameters)
{
    (void)pvParameters;
    for (;;) {
        uint32_t data;
        if (xQueueReceive(xAppQueue, &data, portMAX_DELAY) == pdPASS) {
            data++;
        }
    }
}

static void vMonTask(void *pvParameters)
{
    (void)pvParameters;
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

int main(void)
{
    xAppQueue = xQueueCreate(10, sizeof(uint32_t));
    configASSERT(xAppQueue != NULL);

    xTaskCreate(vAppTask, "App", configMINIMAL_STACK_SIZE * 2, NULL, tskIDLE_PRIORITY + 2, NULL);
    xTaskCreate(vMonTask, "Mon", configMINIMAL_STACK_SIZE, NULL, tskIDLE_PRIORITY + 1, NULL);

    vTaskStartScheduler();
    for (;;) {}
    return 0;
}
