/*
 * MISRA Benchmark — Medium 008: False Negative
 * Rule: MISRA C:2023 Rule 10.6 — The value of a composite expression shall not be assigned
 *          to an object with wider essential type
 *
 * The expression (a + b) is evaluated in uint8_t range before widening.
 * This is an implicit narrowing that may not be detected.
 *
 * Expected: One violation
 */
#include <stdint.h>

uint16_t calculate_sum(uint8_t a, uint8_t b) {
    /* Expression evaluated in uint8_t before assignment to uint16_t  [FN risk] */
    uint16_t sum = a + b;  /* MISRA 10.6: composite expression widened on assignment */
    return sum;
}
