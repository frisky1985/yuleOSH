/*
 * MISRA Benchmark — Case 007: True Negative (no violation)
 * Rule: All — this code should pass cleanly
 *
 * Demonstrates correct MISRA C:2023 compliant coding patterns.
 *
 * Expected: Zero violations
 */
#include <stdint.h>
#include <stdbool.h>

/* Properly typed function */
static uint32_t compute_sum(uint32_t a, uint32_t b) {
    return a + b;
}

/* Boolean-typed return */
static bool is_valid(uint32_t value) {
    return (value > 0U) ? true : false;
}

/* Const-correct pointer parameter */
static uint32_t safe_read(const volatile uint32_t *reg) {
    return *reg;
}

int main(void) {
    uint32_t result;
    bool valid;

    result = compute_sum(100U, 200U);
    valid = is_valid(result);

    if (valid) {
        (void)safe_read((const volatile uint32_t *)0x40000000U);
    }

    (void)result;
    return 0;
}
