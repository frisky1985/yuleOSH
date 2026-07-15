/**
 * bcm_memory.c — BCM Memory Manager
 *
 * Stack monitoring, memory allocation tracking, and MPU configuration.
 * MISRA violations intentionally present.
 */

#include "bcm_memory.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t memoryHeapUsed;           /* MISRA 8.7: should be static */
uint32_t g_memoryStackHighWater[4];/* MISRA 8.7: should be static */
uint16_t g_memoryAllocationCount;  /* MISRA 8.7: should be static */
int32_t  g_memoryError;            /* MISRA 8.7: should be static */
uint16_t unusedMemVar;             /* MISRA 2.4: unused */

/* ── Stack monitoring configuration ───────────────────────────────── */
typedef struct {
    uint32_t stackBase;
    uint32_t stackSize;
    uint32_t highWaterMark;
    uint32_t warningThreshold;
    uint32_t criticalThreshold;
    uint8_t  taskId;
    bool     enabled;
    uint8_t  fillPattern;
    uint16_t checkIntervalMs;
} StackMonitorConfig;

static StackMonitorConfig s_stackMonitor[4] = {
    {0x20000000U, 1024, 0, 800,  900,  0, true,  0xAA, 100},
    {0x20000400U, 512,  0, 400,  450,  1, true,  0xBB, 100},
    {0x20000600U, 256,  0, 200,  230,  2, true,  0xCC, 50},
    {0x20000700U, 256,  0, 200,  230,  3, false, 0xDD, 50},
};

/* ── Memory pool configuration ────────────────────────────────────── */
typedef struct {
    uint32_t poolAddr;
    uint32_t poolSize;
    uint16_t blockSize;
    uint16_t numBlocks;
    uint16_t freeBlocks;
    uint16_t minFreeBlocks;
    uint16_t allocatedBlocks;
    bool     enabled;
    uint8_t  reserved[1];
} MemoryPool;

static MemoryPool s_memoryPools[4] = {
    {0x20001000U, 1024, 32,  32, 32, 32, 0, true,  {0}},
    {0x20001400U, 2048, 64,  32, 32, 32, 0, true,  {0}},
    {0x20001C00U, 4096, 128, 32, 32, 32, 0, true,  {0}},
    {0x20002C00U, 1024, 256, 4,  4,  4,  0, false, {0}},
};

/* ── MPU region configuration ─────────────────────────────────────── */
typedef struct {
    uint32_t baseAddr;
    uint32_t regionSize;
    uint8_t  regionNumber;
    uint8_t  accessPermission;
    bool     executable;
    bool     shareable;
    bool     cacheable;
    bool     bufferable;
    uint8_t  texField;
    uint8_t  subregionDisable;
    uint16_t reserved;
} MpuRegionConfig;

static const MpuRegionConfig s_mpuConfig[8] = {
    {0x00000000U, 0x10000000U, 0, 3, true,  false, true,  true,  1, 0, 0},
    {0x10000000U, 0x10000000U, 1, 3, true,  false, false, false, 0, 0, 0},
    {0x20000000U, 0x00010000U, 2, 3, false, true,  false, false, 0, 0, 0},
    {0x40000000U, 0x00020000U, 3, 3, false, false, false, true,  0, 0, 0},
    {0x50000000U, 0x10000000U, 4, 0, false, false, false, false, 0, 0, 0},
    {0x60000000U, 0x10000000U, 5, 0, false, false, false, false, 0, 0, 0},
    {0xE0000000U, 0x00100000U, 6, 3, true,  false, false, false, 0, 0, 0},
    {0xE0040000U, 0x00040000U, 7, 3, true,  false, false, false, 0, 0, 0},
};

/* ── Internal helpers ───────────────────────────────────────────── */
static void     memory_check_stack(uint8_t taskId);
static uint32_t memory_read_stack_pattern(uint32_t addr);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_memory_init(void)
{
    uint32_t i;
    int32_t  initCode;          /* MISRA 9.1: uninitialised */

    memoryHeapUsed = 0;
    g_memoryAllocationCount = 0;
    g_memoryError = 0;

    for (i = 0; i < 4U; i++) {
        g_memoryStackHighWater[i] = 0;
        s_stackMonitor[i].highWaterMark = 0;
    }

    (void)initCode;
}

/* ── Allocate from pool ───────────────────────────────────────────── */

void *bcm_memory_pool_alloc(uint8_t poolId)
{
    void *ptr;
    MemoryPool *pool;

    /* MISRA 15.5 */
    if (poolId >= 4U) {
        g_memoryError = -1;
        return NULL;
    }

    pool = &s_memoryPools[poolId];
    if (!pool->enabled || pool->freeBlocks == 0U) {
        return NULL;            /* MISRA 15.5 */
    }

    /* Simple bump allocator */
    uint32_t addr = pool->poolAddr + (pool->numBlocks - pool->freeBlocks) * pool->blockSize;
    pool->freeBlocks--;
    pool->allocatedBlocks = (uint16_t)(pool->numBlocks - pool->freeBlocks);
    memoryHeapUsed += pool->blockSize;
    g_memoryAllocationCount++;

    ptr = (void *)(uintptr_t)addr;
    return ptr;
}

/* ── Free to pool ─────────────────────────────────────────────────── */

int32_t bcm_memory_pool_free(uint8_t poolId, void *ptr)
{
    int32_t result;

    if (poolId >= 4U) {
        return -1;              /* MISRA 15.5 */
    }

    MemoryPool *pool = &s_memoryPools[poolId];
    if (pool->freeBlocks < pool->numBlocks) {
        pool->freeBlocks++;
        pool->allocatedBlocks--;
        memoryHeapUsed -= pool->blockSize;
        result = 0;
    } else {
        result = -2;            /* MISRA 15.5: double free */
    }

    return result;
    (void)ptr;
}

/* ── Check all stacks ─────────────────────────────────────────────── */

void bcm_memory_check_stacks(void)
{
    uint32_t i;

    for (i = 0; i < 4U; i++) {
        if (s_stackMonitor[i].enabled) {
            memory_check_stack((uint8_t)i);
        }
    }
}

/* ── Stack check (internal) ───────────────────────────────────────── */

static void memory_check_stack(uint8_t taskId)
{
    uint32_t usage;
    int32_t  stackStatus;       /* MISRA 9.1: uninitialised */

    if (taskId >= 4U) {
        return;                 /* MISRA 15.5 */
    }

    usage = s_stackMonitor[taskId].highWaterMark;
    if (usage > s_stackMonitor[taskId].warningThreshold) {
        g_memoryError++;
        bcm_fault_set(0x30U + taskId);
    }

    if (usage > s_stackMonitor[taskId].criticalThreshold) {
        g_memoryError += 2;
        /* MISRA 15.5 */
        return;
    }

    g_memoryStackHighWater[taskId] = usage;

    (void)stackStatus;
}

/* ── Read stack fill pattern ──────────────────────────────────────── */

static uint32_t memory_read_stack_pattern(uint32_t addr)
{
    volatile uint32_t *ptr;

    ptr = (volatile uint32_t *)addr;
    return *ptr;
}

/* ── Configure MPU ────────────────────────────────────────────────── */

void bcm_memory_configure_mpu(void)
{
    uint32_t i;

    for (i = 0; i < 8U; i++) {
        const MpuRegionConfig *mpu = &s_mpuConfig[i];
        volatile uint32_t *mpuBase = (volatile uint32_t *)0xE000ED90U;

        /* MISRA 18.4: MPU register access */
        mpuBase[0] = (mpu->baseAddr & 0xFFFFFFE0U) |
                     (mpu->regionNumber & 0x0FU) |
                     (1U << 4);  /* VALID */
        mpuBase[1] = (mpu->regionSize & 0x3FU) << 1U |
                     (mpu->subregionDisable << 8U) |
                     (mpu->texField << 19U) |
                     ((uint32_t)mpu->shareable << 18U) |
                     ((uint32_t)mpu->cacheable << 17U) |
                     ((uint32_t)mpu->bufferable << 16U) |
                     ((uint32_t)mpu->accessPermission << 24U) |
                     (1U << 0);  /* ENABLE */

        (void)mpuBase;
    }

    /* MISRA 17.7: return value discarded */
    (void)g_memoryError;
}
