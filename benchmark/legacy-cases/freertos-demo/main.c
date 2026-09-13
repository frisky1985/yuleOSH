/*
 * FreeRTOS 代表性样例（脱敏 stand-in，非真实仓库代码）。
 * 许可证：MIT（与上游 FreeRTOS 内核一致）。
 * 覆盖：任务函数、队列、Cortex-M 风格 ISR 命名（*_IRQHandler）、
 *       xQueueSendFromISR 潜在调用、优先级对象宏、volatile 全局。
 */
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"

#define MAIN_TASK_PRIORITY (tskIDLE_PRIORITY + 1)
#define UART_TASK_PRIORITY (tskIDLE_PRIORITY + 2)
#define QUEUE_LEN 16
#define STACK_DEPTH 128

/* volatile 全局：ISR 与主循环共享 */
volatile BaseType_t g_uart_busy = pdFALSE;

static QueueHandle_t g_cmd_queue;

/* 任务函数（函数定义，命名不含 isr/irq） */
void vMainTask(void *pvParameters)
{
    int cmd = 0;
    for (;;) {
        if (xQueueReceive(g_cmd_queue, &cmd, portMAX_DELAY) == pdTRUE) {
            g_uart_busy = pdTRUE;
            cmd += 1;
        }
    }
}

/* UART 任务 */
void vUartTask(void *pvParameters)
{
    for (;;) {
        if (g_uart_busy == pdTRUE) {
            g_uart_busy = pdFALSE;
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

/* Cortex-M ISR（命名启发式命中 *_IRQHandler） */
void USART1_IRQHandler(void)
{
    BaseType_t xHigherPriorityTaskWoken = pdFALSE;
    int cmd = 7;
    xQueueSendFromISR(g_cmd_queue, &cmd, &xHigherPriorityTaskWoken);
    portYIELD_FROM_ISR(xHigherPriorityTaskWoken);
}

int app_start(void)
{
    g_cmd_queue = xQueueCreate(QUEUE_LEN, sizeof(int));
    if (g_cmd_queue == NULL) {
        return -1;
    }
    xTaskCreate(vMainTask, "main", STACK_DEPTH, NULL, MAIN_TASK_PRIORITY, NULL);
    xTaskCreate(vUartTask, "uart", STACK_DEPTH, NULL, UART_TASK_PRIORITY, NULL);
    vTaskStartScheduler();
    return 0;
}
