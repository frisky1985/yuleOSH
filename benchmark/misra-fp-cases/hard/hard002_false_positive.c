/*
 * MISRA Benchmark — Hard 002: False Positive
 * Rule: MISRA C:2023 Rule 18.6 — The address of an object with automatic storage
 *          shall not be used after the object has ceased to exist
 * Rules: 18.6, 19.1
 *
 * CAN protocol state machine with deferred callback pattern.
 * The callback uses a well-defined lifecycle management pattern common in
 * real-time embedded CAN stacks. cppcheck may flag as use-after-free.
 *
 * Expected: cppcheck false positive (proper lifecycle management)
 */
#include <stdint.h>
#include <stdbool.h>

/* CAN message structure */
typedef struct {
    uint32_t id;
    uint8_t  dlc;
    uint8_t  data[8];
    uint32_t timestamp;
} can_message_t;

/* CAN callback type */
typedef void (*can_rx_cb_t)(const can_message_t *msg, void *context);

/* CAN controller state — lifetime managed by init/deinit pair */
typedef struct {
    can_rx_cb_t rx_callback;
    void       *rx_context;
    uint32_t    filter_mask;
    bool        is_active;
} can_controller_t;

static can_controller_t can_state;

void hard_can_init(can_rx_cb_t cb, void *ctx) {
    can_state.rx_callback = cb;
    can_state.rx_context = ctx;
    can_state.is_active = true;
}

void hard_can_deinit(void) {
    can_state.is_active = false;
    can_state.rx_callback = NULL;
    can_state.rx_context = NULL;
}

static void hard_can_receive(const can_message_t *msg) {
    if (can_state.is_active && can_state.rx_callback) {
        can_state.rx_callback(msg, can_state.rx_context);  /* Safe: context is still alive */
    }
}
