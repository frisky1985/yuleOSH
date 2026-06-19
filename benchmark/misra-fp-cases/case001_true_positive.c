/*
 * MISRA Benchmark — Case 001: True Positive
 * Rule: MISRA C:2023 Rule 10.1 — Operands shall not be of inappropriate type
 *
 * Expected: One violation (uint16_t assigned to uint8_t without cast)
 * False positive risk: Low
 */
#include <stdint.h>

void process_sensor(void) {
    uint8_t sensor_val;
    uint16_t raw = 0x1FF;

    sensor_val = raw;  /* MISRA 10.1: assignment between different essential types */
}
