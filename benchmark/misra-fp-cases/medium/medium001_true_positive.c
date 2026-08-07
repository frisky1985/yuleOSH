/*
 * MISRA Benchmark — Medium 001: True Positive
 * Rule: MISRA C:2023 Rule 8.7 — Functions and variables should not be defined with external linkage
 *          if they are referenced in only one translation unit
 *
 * Expected: One violation (global variable used in only one function)
 * False positive risk: Medium — globals may be accessed through inline asm
 */
#include <stdint.h>

/* This variable is only referenced in process_data, should be static */
uint32_t global_timestamp = 0;  /* MISRA 8.7: external linkage but single-TU use */

static void process_data(void) {
    global_timestamp = 100;
}

void run_medium_001(void) {
    process_data();
}
