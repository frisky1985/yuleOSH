/*
 * MISRA Benchmark — Hard 001: True Positive
 * Rule: MISRA C:2023 Dir 4.12 — Dynamic memory allocation shall not be used
 * Rules: Dir 4.12, 21.3
 *
 * Embedded firmware using malloc/free for variable-length configuration.
 * Dynamic allocation in safety-critical systems is completely prohibited.
 *
 * Expected: Three violations (malloc, free, calloc usage)
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    uint32_t id;
    uint8_t  data[64];
} config_item_t;

static config_item_t *config_pool = NULL;

int hard_init_config(uint32_t count) {
    /* MISRA Dir 4.12: dynamic allocation prohibited */
    config_pool = (config_item_t *)malloc(count * sizeof(config_item_t));
    /* MISRA 21.3: memory allocation functions prohibited */
    if (!config_pool) {
        return -1;
    }
    memset(config_pool, 0, count * sizeof(config_item_t));
    return 0;
}

void hard_cleanup_config(void) {
    free(config_pool);       /* MISRA Dir 4.12: free() prohibited */
    config_pool = NULL;
}
