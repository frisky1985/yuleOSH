/*
 * MISRA Benchmark — Case 008: False Negative Risk
 * Rule: MISRA C:2023 Rule 13.3 — side effects in evaluation order
 *
 * This code has a potential evaluation order dependency that cppcheck
 * may NOT flag (false negative). The expression `*p++ = ++i` depends on
 * evaluation order.
 *
 * Expected: cppcheck may miss this (false negative)
 */
#include <stdint.h>

void ambiguous_assign(uint32_t *arr) {
    uint32_t i = 0U;
    uint32_t *p = arr;

    /* Evaluation order dependency — two side effects in one expression */
    *p++ = ++i;  /* MISRA 13.3: side effects on p AND i */
}
