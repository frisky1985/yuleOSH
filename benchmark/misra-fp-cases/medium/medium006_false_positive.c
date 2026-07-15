/*
 * MISRA Benchmark — Medium 006: False Positive
 * Rule: MISRA C:2023 Rule 8.13 — A pointer to a function shall not be assigned a
 *          pointer to a non-function or vice versa
 *
 * RTOS callback registration — function pointers of compatible signature.
 * cppcheck may incorrectly flag the cast in the generic registration macro.
 *
 * Expected: cppcheck false positive
 */
#include <stdint.h>

/* RTOS timer callback type */
typedef void (*timer_callback_t)(void *param);

/* Generic registration — common RTOS pattern */
#define REGISTER_TIMER(name, cb, period_ms) \
    static timer_callback_t _cb_##name = (timer_callback_t)(cb)

/* User callback with different but compatible signature */
static void my_timer_handler(uint32_t id) {
    (void)id;
}

REGISTER_TIMER(sensor_poll, my_timer_handler, 100);
