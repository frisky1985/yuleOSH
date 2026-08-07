/*
 * MISRA Benchmark — Medium 003: True Positive
 * Rule: MISRA C:2023 Rule 10.3 — The value of an expression shall not be assigned to an
 *          object with a narrower essential type or of a different essential type category
 * Rules: 10.3, 10.4
 *
 * Expected: Two violations (implicit narrowing from int32_t to int16_t, mixed signedness)
 * False positive risk: Low
 */
#include <stdint.h>

void compute_sensor(int32_t raw) {
    int16_t result;
    uint16_t positive_only;

    result = raw;            /* MISRA 10.3: int32_t to int16_t without range check */
    positive_only = raw;     /* MISRA 10.4: different signedness cast */
}
