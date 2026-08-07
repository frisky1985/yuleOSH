/*
 * MISRA Benchmark — Hard 003: True Negative
 * Rule: MISRA C:2023 Rule 22.1 — All resources obtained dynamically shall be explicitly released
 *
 * Robust TCP connection management with deterministic deallocation
 * and RAII-equivalent cleanup pattern for embedded systems.
 * No leak, double-free, or use-after-free.
 *
 * Expected: Zero violations
 */
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* TCP buffer pool — pre-allocated, no dynamic allocation */
#define TCP_POOL_SIZE 4
#define TCP_BUF_SIZE  2048

typedef struct {
    uint8_t  data[TCP_BUF_SIZE];
    uint32_t len;
    bool     in_use;
} tcp_buffer_t;

static tcp_buffer_t tcp_pool[TCP_POOL_SIZE];

static tcp_buffer_t *hard_tcp_acquire_buffer(void) {
    for (int i = 0; i < TCP_POOL_SIZE; i++) {
        if (!tcp_pool[i].in_use) {
            tcp_pool[i].in_use = true;
            tcp_pool[i].len = 0;
            memset(tcp_pool[i].data, 0, TCP_BUF_SIZE);
            return &tcp_pool[i];
        }
    }
    return NULL;
}

static void hard_tcp_release_buffer(tcp_buffer_t *buf) {
    if (buf && buf->in_use) {
        buf->in_use = false;
        buf->len = 0;
    }
}

void hard_tcp_process(void) {
    tcp_buffer_t *buf = hard_tcp_acquire_buffer();
    if (buf) {
        /* Process data */
        buf->len = 128;
        hard_tcp_release_buffer(buf);  /* Always released */
    }
}
