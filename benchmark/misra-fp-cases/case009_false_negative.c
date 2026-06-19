/*
 * MISRA Benchmark — Case 009: False Negative Risk
 * Rule: MISRA C:2023 Rule 18.2 — pointer arithmetic only on array elements
 *
 * Incrementing past end of array is undefined behavior.
 * Some simple tools may not detect this.
 *
 * Expected: cppcheck may miss this (false negative)
 */
#include <stdint.h>

void buffer_overflow(void) {
    uint32_t buffer[10];
    uint32_t *ptr = buffer;

    /* Advance past end of array — undefined behavior */
    for (int i = 0; i <= 10; i++) {  /* off-by-one */
        *ptr = i;
        ptr++;
    }
}
