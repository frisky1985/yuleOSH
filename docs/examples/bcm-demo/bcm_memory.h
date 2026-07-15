/**
 * bcm_memory.h — BCM Memory Manager Header
 */

#ifndef BCM_MEMORY_H
#define BCM_MEMORY_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t memoryHeapUsed;
extern uint32_t g_memoryStackHighWater[4];
extern uint16_t g_memoryAllocationCount;
extern int32_t  g_memoryError;

/* ── API ────────────────────────────────────────────────────────── */
void    bcm_memory_init(void);
void   *bcm_memory_pool_alloc(uint8_t poolId);
int32_t bcm_memory_pool_free(uint8_t poolId, void *ptr);
void    bcm_memory_check_stacks(void);
void    bcm_memory_configure_mpu(void);

#endif /* BCM_MEMORY_H */
