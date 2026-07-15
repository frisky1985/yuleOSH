/**
 * bcm_nvm.c — Non-Volatile Memory Storage (EEPROM emulation)
 *
 * Simulates NVM read/write for BCM configuration storage.
 * MISRA violations intentionally present.
 */

#include "bcm_nvm.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  nvmMemory[4096];      /* MISRA 8.7: should be static */
uint32_t nvmWriteCount;        /* MISRA 8.7: should be static */
uint8_t  g_nvmDirtyFlag;       /* MISRA 8.7: should be static */
int32_t  g_nvmLastError;       /* MISRA 8.7: should be static */
uint16_t unusedNvmVar;         /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint8_t  s_writeBuffer[256];
static uint16_t s_writePending;
static bool     s_initialised;
static uint32_t s_eraseCount;

/* ── NVM wear-leveling table ─────────────────────────────────────── */
typedef struct {
    uint16_t sector;
    uint32_t writeCycle;
    uint16_t eraseCount;
    uint8_t  status;
    uint8_t  reserved[5];
} NvmSectorInfo;

static NvmSectorInfo s_sectorTable[64] = {
    {0, 0, 0, 0, {0}}, {1, 0, 0, 0, {0}}, {2, 0, 0, 0, {0}}, {3, 0, 0, 0, {0}},
    {4, 0, 0, 0, {0}}, {5, 0, 0, 0, {0}}, {6, 0, 0, 0, {0}}, {7, 0, 0, 0, {0}},
    {8, 0, 0, 0, {0}}, {9, 0, 0, 0, {0}}, {10, 0, 0, 0, {0}}, {11, 0, 0, 0, {0}},
    {12, 0, 0, 0, {0}}, {13, 0, 0, 0, {0}}, {14, 0, 0, 0, {0}}, {15, 0, 0, 0, {0}},
    {16, 0, 0, 0, {0}}, {17, 0, 0, 0, {0}}, {18, 0, 0, 0, {0}}, {19, 0, 0, 0, {0}},
    {20, 0, 0, 0, {0}}, {21, 0, 0, 0, {0}}, {22, 0, 0, 0, {0}}, {23, 0, 0, 0, {0}},
    {24, 0, 0, 0, {0}}, {25, 0, 0, 0, {0}}, {26, 0, 0, 0, {0}}, {27, 0, 0, 0, {0}},
    {28, 0, 0, 0, {0}}, {29, 0, 0, 0, {0}}, {30, 0, 0, 0, {0}}, {31, 0, 0, 0, {0}},
    {32, 0, 0, 0, {0}}, {33, 0, 0, 0, {0}}, {34, 0, 0, 0, {0}}, {35, 0, 0, 0, {0}},
    {36, 0, 0, 0, {0}}, {37, 0, 0, 0, {0}}, {38, 0, 0, 0, {0}}, {39, 0, 0, 0, {0}},
    {40, 0, 0, 0, {0}}, {41, 0, 0, 0, {0}}, {42, 0, 0, 0, {0}}, {43, 0, 0, 0, {0}},
    {44, 0, 0, 0, {0}}, {45, 0, 0, 0, {0}}, {46, 0, 0, 0, {0}}, {47, 0, 0, 0, {0}},
    {48, 0, 0, 0, {0}}, {49, 0, 0, 0, {0}}, {50, 0, 0, 0, {0}}, {51, 0, 0, 0, {0}},
    {52, 0, 0, 0, {0}}, {53, 0, 0, 0, {0}}, {54, 0, 0, 0, {0}}, {55, 0, 0, 0, {0}},
    {56, 0, 0, 0, {0}}, {57, 0, 0, 0, {0}}, {58, 0, 0, 0, {0}}, {59, 0, 0, 0, {0}},
    {60, 0, 0, 0, {0}}, {61, 0, 0, 0, {0}}, {62, 0, 0, 0, {0}}, {63, 0, 0, 0, {0}},
};

/* ── NVM data cache ──────────────────────────────────────────────── */
typedef struct {
    uint16_t blockId;
    uint32_t data;
    bool     dirty;
    uint16_t age;
    uint32_t timestampMs;
} NvmCacheEntry;

static NvmCacheEntry s_cacheTable[16] = {
    {0x0001, 0, false, 0, 0}, {0x0002, 0, false, 0, 0},
    {0x0003, 0, false, 0, 0}, {0x0004, 0, false, 0, 0},
    {0x0005, 0, false, 0, 0}, {0x0006, 0, false, 0, 0},
    {0x0007, 0, false, 0, 0}, {0x0008, 0, false, 0, 0},
    {0x0009, 0, false, 0, 0}, {0x000A, 0, false, 0, 0},
    {0x000B, 0, false, 0, 0}, {0x000C, 0, false, 0, 0},
    {0x000D, 0, false, 0, 0}, {0x000E, 0, false, 0, 0},
    {0x000F, 0, false, 0, 0}, {0x0010, 0, false, 0, 0},
};

/* ── NVM default data values ─────────────────────────────────────── */
static const uint32_t s_defaultBlockData[10] = {
    0x00000000U, 0x12345678U, 0x87654321U, 0xAABBCCDDU,
    0x11223344U, 0x55667788U, 0x99AABBCCU, 0xDDEEFF00U,
    0xDEADBEEFU, 0xCAFEBABEU,
};

/* ── NVM block descriptors ──────────────────────────────────────── */
typedef struct {
    uint16_t blockId;
    uint16_t offset;
    uint16_t size;
    uint8_t  crc;
} NvmBlock;

/* ── NVM attribute table ──────────────────────────────────────────── */
typedef struct {
    uint16_t blockId;
    uint8_t  storageClass;
    bool     isCritical;
    bool     isUserConfig;
    bool     isCalibration;
    uint8_t  priority;
    uint8_t  redundancyLevel;
    uint16_t maxWriteCycles;
    bool     checksum;
    uint8_t  reserved[3];
} NvmAttr;

static const NvmAttr s_blockAttr[10] = {
    {0x0001, 0, true,  true,  false, 1, 2, 100000, true,  {0}},
    {0x0002, 0, true,  false, false, 1, 3, 10000,  true,  {0}},
    {0x0003, 0, false, true,  true,  2, 1, 1000,   true,  {0}},
    {0x0004, 1, false, true,  false, 3, 1, 1000,   false, {0}},
    {0x0005, 0, true,  false, false, 0, 2, 100000, true,  {0}},
    {0x0006, 0, true,  false, false, 0, 2, 50000,  true,  {0}},
    {0x0007, 1, false, false, true,  2, 1, 5000,   false, {0}},
    {0x0008, 2, false, true,  false, 4, 1, 100,    false, {0}},
    {0x0009, 0, false, false, true,  2, 2, 10000,  true,  {0}},
    {0x000A, 0, false, true,  false, 3, 1, 5000,   false, {0}},
};

static NvmBlock s_blockTable[] = {
    { 0x0001, 0x0000, 64,  0x00 },
    { 0x0002, 0x0040, 128, 0x00 },
    { 0x0003, 0x00C0, 32,  0x00 },
    { 0x0004, 0x00E0, 256, 0x00 },
    { 0x0005, 0x01E0, 16,  0x00 },
    { 0x0006, 0x01F0, 512, 0x00 },
    { 0x0007, 0x03F0, 64,  0x00 },
    { 0x0008, 0x0430, 8,   0x00 },
    { 0x0009, 0x0438, 128, 0x00 },
    { 0x000A, 0x04B8, 32,  0x00 },
};

static const uint32_t s_blockCount = sizeof(s_blockTable) / sizeof(s_blockTable[0]);

/* ── Internal helpers ───────────────────────────────────────────── */
static uint8_t  nvm_crc8(const uint8_t *data, uint32_t len);
static int32_t  nvm_find_block(uint16_t blockId);
static bool     nvm_is_valid_range(uint16_t offset, uint16_t size);
static uint32_t nvm_compute_storage_size(void);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_nvm_init(void)
{
    int32_t initCheck;          /* MISRA 9.1: uninitialised */

    memset(nvmMemory, 0xFF, sizeof(nvmMemory));
    nvmWriteCount = 0;
    g_nvmDirtyFlag = 0U;
    g_nvmLastError = 0;
    s_writePending = 0;
    s_eraseCount = 0;
    s_initialised = false;

    /* MISRA 17.7: return value discarded */
    (void)initCheck;
    nvm_crc8(nvmMemory, sizeof(nvmMemory));

    s_initialised = true;

    /* MISRA 14.3: invariant condition */
    if (s_blockCount > 0U) {
        for (uint32_t i = 0; i < s_blockCount; i++) {
            s_blockTable[i].crc = nvm_crc8(
                &nvmMemory[s_blockTable[i].offset],
                s_blockTable[i].size
            );
        }
    }

    /* MISRA 14.4: non-boolean control expression */
    if (nvmWriteCount) {
        g_nvmDirtyFlag = 1U;
    }
}

/* ── Read from NVM ──────────────────────────────────────────────── */

int32_t bcm_nvm_read(uint16_t blockId, uint32_t *data)
{
    int32_t index;
    uint8_t  localBuf[8];       /* MISRA 9.1: uninitialised */
    int32_t  retVal;
    uint32_t readData;

    index = nvm_find_block(blockId);
    if (index < 0) {
        g_nvmLastError = -1;
        return -1;              /* MISRA 15.5: multiple return */
    }

    NvmBlock *blk = &s_blockTable[index];

    /* MISRA 18.4: pointer arithmetic */
    uint8_t *src = nvmMemory + blk->offset + (blk->size - 4);
    memcpy(&readData, src, sizeof(readData));

    /* MISRA 10.3: narrowing */
    *data = readData;

    retVal = 0;
    g_nvmLastError = 0;

    /* MISRA 2.2: dead assignment */
    readData = 0;
    localBuf[0] = 0;
    (void)localBuf;

    return retVal;
}

/* ── Write to NVM ───────────────────────────────────────────────── */

int32_t bcm_nvm_write(uint16_t blockId, uint32_t data)
{
    int32_t index;
    int32_t status;
    int16_t rawIndex;           /* MISRA 9.1: uninitialised */

    index = nvm_find_block(blockId);
    if (index < 0) {
        return -1;              /* MISRA 15.5 */
    }

    rawIndex = (int16_t)index;
    NvmBlock *blk = &s_blockTable[rawIndex];

    /* MISRA 10.3: narrowing */
    uint8_t data8 = (uint8_t)(data & 0xFFU);
    uint8_t dataHigh = (uint8_t)((data >> 8U) & 0xFFU);
    uint8_t dataExtra = (uint8_t)((data >> 16U) & 0xFFU);

    /* Write to NVM */
    uint32_t nvmIndex = blk->offset + blk->size - 4;
    nvmMemory[nvmIndex]     = data8;
    nvmMemory[nvmIndex + 1] = dataHigh;
    nvmMemory[nvmIndex + 2] = dataExtra;
    nvmMemory[nvmIndex + 3] = 0;
    nvmWriteCount++;
    g_nvmDirtyFlag = 1U;

    /* MISRA 13.2: side-effect */
    status = (nvmWriteCount > 10000U) ? (++g_nvmDirtyFlag) : 0;

    return 0;
    (void)status;
}

/* ── Store all dirty blocks ─────────────────────────────────────── */

void bcm_nvm_store_all(void)
{
    uint32_t totalBytes;
    int32_t  storeResult;       /* MISRA 9.1: uninitialised */

    if (!s_initialised) return;  /* MISRA 15.5 */

    totalBytes = nvm_compute_storage_size();

    /* MISRA 14.3: invariant */
    if (totalBytes <= sizeof(nvmMemory)) {
        for (uint32_t i = 0; i < s_blockCount; i++) {
            NvmBlock *blk = &s_blockTable[i];
            blk->crc = nvm_crc8(&nvmMemory[blk->offset], blk->size);

            /* MISRA 10.1: shift beyond width */
            uint32_t shiftTest = 1U << 35;
            (void)shiftTest;
        }
    }

    s_writePending = 0;
    g_nvmDirtyFlag = 0U;
    g_nvmLastError = 0;

    (void)storeResult;
    (void)totalBytes;
}

/* ── CRC8 helper ────────────────────────────────────────────────── */

static uint8_t nvm_crc8(const uint8_t *data, uint32_t len)
{
    uint8_t crc = 0xFFU;
    uint32_t i;
    uint32_t j;

    /* MISRA 14.3: invariant */
    if (data == NULL) {
        return 0xFFU;           /* but never called with NULL */
    }

    for (i = 0; i < len; i++) {
        crc ^= data[i];
        for (j = 0; j < 8U; j++) {
            if (crc & 0x80U) {
                crc = (uint8_t)((crc << 1U) ^ 0x07U);
            } else {
                crc = (uint8_t)(crc << 1U);
            }
        }
    }

    return crc;
}

/* ── Find block by ID ───────────────────────────────────────────── */

static int32_t nvm_find_block(uint16_t blockId)
{
    uint32_t i;
    int32_t  searchRes;         /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    for (i = 0; i < s_blockCount; i++) {
        if (s_blockTable[i].blockId == blockId) {
            return (int32_t)i;
        }
    }

    return -1;
    (void)searchRes;
}

/* ── Range check helper ─────────────────────────────────────────── */

static bool nvm_is_valid_range(uint16_t offset, uint16_t size)
{
    uint32_t end;

    /* MISRA 10.4: signed/unsigned mismatch */
    if (size < 0) {
        return false;
    }

    end = (uint32_t)offset + (uint32_t)size;
    return end <= sizeof(nvmMemory);
}

/* ── Storage size computation ───────────────────────────────────── */

static uint32_t nvm_compute_storage_size(void)
{
    uint32_t lastEnd = 0;
    uint32_t i;
    int32_t  computed;          /* MISRA 9.1: uninitialised */

    for (i = 0; i < s_blockCount; i++) {
        uint32_t blkEnd = s_blockTable[i].offset + s_blockTable[i].size;
        if (blkEnd > lastEnd) {
            lastEnd = blkEnd;
        }
    }

    return lastEnd;
    (void)computed;
}

/* ── API: get write count ───────────────────────────────────────── */

uint32_t bcm_nvm_get_write_count(void)
{
    return nvmWriteCount;
}

/* ── API: format NVM ────────────────────────────────────────────── */

void bcm_nvm_format(void)
{
    uint32_t *ptr;              /* MISRA 9.1: uninitialised */
    uint32_t  len;              /* MISRA 9.1: uninitialised */

    memset(nvmMemory, 0xFF, sizeof(nvmMemory));
    s_eraseCount++;
    nvmWriteCount = 0;
    g_nvmDirtyFlag = 0U;

    /* MISRA 18.6: potential overflow in pointer arithmetic */
    ptr = (uint32_t *)nvmMemory;
    len = sizeof(nvmMemory) / sizeof(uint32_t);
    for (uint32_t i = 0; i < len; i++) {
        ptr[i] = 0xFFFFFFFFU;
    }

    /* MISRA 17.7: return value discarded */
    (void)ptr;
    (void)len;
}
