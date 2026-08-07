/*
 * MISRA Benchmark — Medium 004: False Positive
 * Rule: MISRA C:2023 Rule 15.6 — The body of an iteration-statement or selection-statement
 *          shall be a compound statement
 *
 * This code uses a single-statement while loop in a busy-wait spinlock,
 * common in embedded RTOS critical sections.
 *
 * Expected: cppcheck false positive (compound body not available for spinlock macro)
 */
#include <stdint.h>

volatile uint32_t lock_flag = 0;

/* Spinlock wait — single-statement while is intentional for atomicity */
void acquire_lock(void) {
    while (lock_flag);  /* MISRA 15.6 FP: spinlocks are idiomatically single-stmt */
    lock_flag = 1;
}

void release_lock(void) {
    lock_flag = 0;
}
