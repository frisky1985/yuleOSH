/*
 * MISRA Benchmark — Case 002: False Positive Risk
 * Rule: MISRA C:2023 Rule 11.3 — cast pointer to integral type
 *
 * This code uses a uintptr_t cast which is common in embedded HAL drivers.
 * cppcheck may flag as violation even though uintptr_t is explicitly
 * designed for this purpose.
 *
 * Expected: cppcheck false positive
 */
#include <stdint.h>

void write_to_register(uint32_t reg_addr, uint32_t value) {
    /* uintptr_t cast for MMIO access — common embedded pattern */
    volatile uint32_t *reg = (volatile uint32_t *)(uintptr_t)reg_addr;
    *reg = value;
}
