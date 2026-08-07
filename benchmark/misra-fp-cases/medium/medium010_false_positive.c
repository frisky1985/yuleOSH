/*
 * MISRA Benchmark — Medium 010: False Positive
 * Rule: MISRA C:2023 Rule 18.1 — A pointer resulting from arithmetic on a pointer operand
 *          shall address an element of the same array as that pointer operand
 *
 * Embedded DMA buffer management — ring buffer with pointer wraparound.
 * cppcheck may incorrectly flag offset calculation.
 *
 * Expected: cppcheck false positive (0 real violations)
 */
#include <stdint.h>

#define BUF_SIZE 256

typedef struct {
    uint8_t data[BUF_SIZE];
    uint32_t head;
    uint32_t tail;
} ringbuf_t;

static uint8_t ringbuf_read(ringbuf_t *rb) {
    uint8_t val;
    if (rb->head != rb->tail) {
        val = rb->data[rb->tail];
        rb->tail = (rb->tail + 1) % BUF_SIZE;  /* Ring buffer wraparound */
    }
    return val;
}
