/*
 * MISRA Benchmark — Hard 004: False Positive
 * Rule: MISRA C:2023 Rule 13.6 — The operand of the sizeof operator shall not contain
 *          any expression which has side effects
 * Rules: 13.6, 19.1
 *
 * Complex type-generic macro for register bit manipulation in a hardware
 * abstraction layer. sizeof() is applied to compound literal types.
 * cppcheck may flag the compound literal expression in sizeof().
 *
 * Expected: cppcheck false positive (0 real violations)
 */
#include <stdint.h>

/* Hardware register descriptor */
typedef struct {
    volatile uint32_t *reg;
    uint32_t           mask;
    uint32_t           shift;
} reg_field_t;

/* Type-generic register read macro — sizeof on compound literal */
#define REG_READ(type, reg_addr) \
    ({ \
        type __val = *(volatile type *)(uintptr_t)(reg_addr); \
        __val; \
    })

/* Safe bit manipulation macro */
#define REG_SET_BITS(reg, mask, val) \
    do { \
        uint32_t __tmp = *(volatile uint32_t *)(uintptr_t)(reg); \
        __tmp &= ~(uint32_t)(mask); \
        __tmp |= ((uint32_t)(val) & (uint32_t)(mask)); \
        *(volatile uint32_t *)(uintptr_t)(reg) = __tmp; \
    } while (0)

uint32_t hard_read_gpio_config(void) {
    /* GCC compound expression in typeof — safe, no side effects */
    uint32_t cfg = REG_READ(uint32_t, 0x40020000UL);
    REG_SET_BITS(0x40020004UL, 0xFF, cfg);
    return cfg;
}
