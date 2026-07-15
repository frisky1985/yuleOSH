/*
 * MISRA Benchmark — Case 011: Mixed Type Math (hybrid)
 * Rules: 10.1, 10.3, 10.4
 *
 * Mixes several essential type categories in arithmetic operations.
 * Some violations are clear, some are borderline.
 *
 * Expected: 2-3 violations depending on tool strictness
 */
#include <stdint.h>

int32_t mixed_calc(uint16_t a, int8_t b, uint32_t c) {
    /* signed + unsigned mismatch */
    int32_t result = a + b;      /* 10.4: signed/unsigned essential type mix */

    /* shift on signed type */
    result |= (c << 2U);         /* 10.1: signed LHS in shift operation */

    return result;
}
