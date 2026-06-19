/*
 * MISRA Benchmark — Case 010: False Negative Risk
 * Rule: MISRA C:2023 Rule 8.2 — function type mismatch (implicit declaration)
 *
 * Calling a function without a prior prototype — classic C pitfall.
 * cppcheck may warn but some newer MISRA checkers miss it.
 *
 * Expected: cppcheck may miss this (false negative)
 */
#include <stdint.h>

/* NOTE: no prototype for external_func() */
void caller(void) {
    /* External function with no visible prototype — MISRA 8.2 violation */
    uint32_t val = external_func(42U, 0.5f);  /* implicit declaration */
    (void)val;
}
