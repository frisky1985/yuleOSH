/*
 * FreeRTOS 通信样例（脱敏 stand-in）。MIT。
 * 覆盖：函数指针回调 + 取址潜在调用（&handler）、嵌套条件 + 宏函数式。
 */
#include "FreeRTOS.h"
#include "semphr.h"

#define COMM_TIMEOUT_MS 50
#define MAX_RETRIES 3

/* 函数式宏：带可变参数的日志（低置信度） */
#define LOG_COMM(fmt, ...) printf(fmt, __VA_ARGS__)

typedef void (*comm_handler_t)(uint8_t *buf, size_t len);

static SemaphoreHandle_t g_tx_sem;
static comm_handler_t g_handler;

void comm_register_handler(comm_handler_t h)
{
    g_handler = h;
}

static int acquire_tx(void)
{
    return xSemaphoreTake(g_tx_sem, pdMS_TO_TICKS(COMM_TIMEOUT_MS));
}

int comm_send(uint8_t *buf, size_t len)
{
    int tries = 0;
    while (tries < MAX_RETRIES) {
        if (acquire_tx() == pdTRUE) {
            LOG_COMM("send %u bytes\n", (unsigned)len);
            if (g_handler != NULL) {
                g_handler(buf, len);
            }
            xSemaphoreGive(g_tx_sem);
            return 0;
        }
        tries += 1;
    }
    return -1;
}
