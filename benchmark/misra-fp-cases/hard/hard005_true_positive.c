/*
 * MISRA Benchmark — Hard 005: True Positive
 * Rule: MISRA C:2023 Dir 1.1 — Any implementation-defined behavior shall be
 *          consistent and documented
 * Rules: Dir 1.1, 10.1, 12.1
 *
 * Mixed essential type arithmetic with implementation-defined bit-field behavior.
 * Embedded firmware with packed struct and implicit type promotions.
 *
 * Expected: Three violations
 */
#include <stdint.h>

/* Packed struct for hardware register map — implementation-defined layout */
typedef struct __attribute__((packed)) {
    uint32_t field_a : 3;   /* Bit-field: implementation-defined layout */
    uint32_t field_b : 5;   /* Bit-field overlap possible */
    uint16_t field_c : 10;  /* Narrow bit-field with wider storage */
} hw_reg_map_t;

static volatile hw_reg_map_t * const hw_regs = (hw_reg_map_t *)(uintptr_t)0x40010000;

uint32_t hard_read_mixed_fields(void) {
    /* Dir 1.1: implementation-defined bit-field behavior */
    uint32_t combined = hw_regs->field_a + hw_regs->field_b;   /* MISRA 10.1: mixed essential types */
    uint32_t shifted = hw_regs->field_c << 6;                   /* MISRA 12.1: shift by non-constant */
    return combined | shifted;
}
