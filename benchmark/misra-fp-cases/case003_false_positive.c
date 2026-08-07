/*
 * MISRA Benchmark — Case 003: False Positive Risk
 * Rule: MISRA C:2023 Rule 8.13 — pointer parameters should be const
 *
 * RTOS callback functions often cannot use const pointers due to API
 * contract. cppcheck may flag this even thouth the function signature
 * is required by FreeRTOS/ThreadX API.
 *
 * Expected: cppcheck false positive
 */
#include <stdint.h>

/* ThreadX entry function signature — cannot add const */
/* cppcheck-suppress [misra-c2023-8.13] — RTOS API contract */
void tx_application_define(void *first_unused_memory) {
    (void)first_unused_memory;
    /* Application initialization */
}

/* FreeRTOS task signature */
/* cppcheck-suppress [misra-c2023-8.13] — RTOS API contract */
void vTaskFunction(void *pvParameters) {
    (void)pvParameters;
    while (1) {
        /* task loop */
    }
}
