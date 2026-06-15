/*
 * Zephyr RTOS Application
 */

#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/logging/log.h>

LOG_MODULE_REGISTER(main, CONFIG_LOG_DEFAULT_LEVEL);

K_SEM_DEFINE(app_sem, 0, 1);

void thread_a_entry(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);

    while (1) {
        LOG_INF("Thread A running");
        k_sem_give(&app_sem);
        k_sleep(K_SECONDS(1));
    }
}

void thread_b_entry(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);

    while (1) {
        k_sem_take(&app_sem, K_FOREVER);
        LOG_INF("Thread B received semaphore");
        k_sleep(K_MSEC(500));
    }
}

void thread_c_entry(void *arg1, void *arg2, void *arg3)
{
    ARG_UNUSED(arg1);
    ARG_UNUSED(arg2);
    ARG_UNUSED(arg3);

    while (1) {
        LOG_INF("Thread C running");
        k_sleep(K_SECONDS(2));
    }
}

int main(void)
{
    LOG_INF("Zephyr RTOS Application Starting");
    return 0;
}
