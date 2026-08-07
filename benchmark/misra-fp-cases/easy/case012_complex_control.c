/*
 * MISRA Benchmark — Case 012: Complex Control Flow
 * Rules: 14.3, 15.6, 16.7
 *
 * Complex control flow with nested conditions, switch fall-through,
 * and loop counter manipulation.
 *
 * Expected: 3-4 violations
 */
#include <stdint.h>
#include <stdbool.h>

typedef enum {
    STATE_IDLE = 0,
    STATE_RUNNING,
    STATE_ERROR,
    STATE_RESET
} state_t;

void state_machine_controller(state_t current) {
    uint32_t counter;

    switch (current) {
    case STATE_IDLE:
        /* Fall-through — expected violation of 16.7 */
    case STATE_RESET:
        counter = 0U;
        break;
    case STATE_RUNNING:
        for (counter = 0U; counter < 10U; counter++) {
            /* Modify loop counter inside loop — 14.3 */
            if (counter == 5U) {
                counter = 10U;  /* loop counter modification */
            }
        }
        break;
    case STATE_ERROR:
        break;
    }
    (void)counter;
}
