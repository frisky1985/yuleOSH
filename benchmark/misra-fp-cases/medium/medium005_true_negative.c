/*
 * MISRA Benchmark — Medium 005: True Negative
 * Rule: MISRA C:2023 Rule 17.2 — Functions shall not call themselves, either directly or indirectly
 *
 * This code is clean — no recursion.
 * cppcheck should not flag any violations.
 *
 * Expected: Zero violations
 */
#include <stdint.h>

static uint32_t factorial_iter(uint32_t n) {
    uint32_t result = 1;
    for (uint32_t i = 2; i <= n; i++) {
        result *= i;
    }
    return result;
}

void safe_math(void) {
    uint32_t val = factorial_iter(10);
    (void)val;
}
