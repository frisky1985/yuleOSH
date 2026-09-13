/*
 * Zephyr 传感器采样样例（脱敏 stand-in）。
 * 许可证：Apache-2.0。
 * 覆盖：函数指针回调（potential-call）、对象宏白名单（NULL 应跳过）、
 *       flag 宏、嵌套条件编译。
 */
#include <zephyr/kernel.h>
#include <zephyr/drivers/sensor.h>

#define SENSOR_POLL_MS 1000
#define ENABLE_FILTER
#define SAMPLE_OK 0

struct sensor_reading {
    double temp;
    double humidity;
};

/* flag 宏（无值，低置信度） */
#define USE_FLOAT

/* 函数指针式回调（潜在调用，不静默丢弃） */
typedef void (*sample_cb_t)(const struct sensor_reading *r);

static sample_cb_t g_callback;

static const struct device *g_sensor_dev;

void register_sample_callback(sample_cb_t cb)
{
    g_callback = cb;
}

static int read_once(struct sensor_reading *out)
{
    if (g_sensor_dev == NULL) {
        return -1;
    }
    out->temp = 21.5;
#ifdef ENABLE_FILTER
    out->humidity = 55.0;
#else
    out->humidity = 0.0;
#endif
    return SAMPLE_OK;
}

void sensor_worker(void)
{
    struct sensor_reading r;
    if (read_once(&r) == SAMPLE_OK) {
        if (g_callback != NULL) {
            g_callback(&r);
        }
    }
}
