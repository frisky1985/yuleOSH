/*
 * MISRA Benchmark — Medium 009: True Negative
 * Rule: MISRA C:2023 Rule 13.2 — The value of an expression and its persistent side effects
 *          shall be the same under all permitted evaluation orders
 *
 * Clean code — no ordering dependencies.
 *
 * Expected: Zero violations
 */
#include <stdint.h>

typedef struct {
    uint32_t x;
    uint32_t y;
} point_t;

static uint32_t safe_add(uint32_t a, uint32_t b) {
    return a + b;
}

point_t compute_midpoint(point_t *p1, point_t *p2) {
    point_t mid;
    mid.x = safe_add(p1->x, p2->x) / 2;
    mid.y = safe_add(p1->y, p2->y) / 2;
    return mid;
}
