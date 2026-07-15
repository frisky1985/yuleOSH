/**
 * bcm_fault.c — BCM Fault Manager
 *
 * Fault detection, logging and DTC management.
 * MISRA violations intentionally present.
 */

#include "bcm_fault.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  faultActiveDtc[16];   /* MISRA 8.7: should be static */
uint32_t faultTotalCount;      /* MISRA 8.7: should be static */
uint8_t  g_faultOverflow;      /* MISRA 8.7: should be static */
int32_t  g_faultInternalState; /* MISRA 8.7: should be static */
uint16_t unusedFaultVar;       /* MISRA 2.4: unused */

/* ── DTC severity mapping table ──────────────────────────────────── */
typedef struct {
    uint8_t  dtcRangeLow;
    uint8_t  dtcRangeHigh;
    uint8_t  defaultSeverity;
    uint8_t  storageClass;
    bool     snapshotOnSet;
    uint8_t  debounceMs;
    uint8_t  enableCondition;
    uint8_t  agingCounter;
    uint16_t snapshotDataSize;
} DtcTypeDef;

static const DtcTypeDef s_dtcTypeDef[32] = {
    {0x01, 0x0F, 3, 0, true,  0,   0, 40, 4},
    {0x10, 0x1F, 2, 0, true,  100, 1, 40, 8},
    {0x20, 0x2F, 2, 0, true,  50,  0, 20, 4},
    {0x30, 0x3F, 1, 1, false, 0,   0, 10, 2},
    {0x40, 0x4F, 3, 0, true,  10,  2, 60, 8},
    {0x50, 0x5F, 2, 0, true,  20,  1, 40, 4},
    {0x60, 0x6F, 1, 0, true,  0,   0, 20, 2},
    {0x70, 0x7F, 3, 0, true,  0,   0, 80, 8},
    {0x80, 0x8F, 2, 0, true,  100, 2, 40, 4},
    {0x90, 0x9F, 1, 1, true,  50,  0, 10, 2},
    {0xA0, 0xAF, 3, 0, true,  0,   0, 60, 8},
    {0xB0, 0xBF, 2, 0, true,  10,  1, 40, 4},
    {0xC0, 0xCF, 1, 0, true,  0,   0, 20, 2},
    {0xD0, 0xDF, 3, 0, true,  0,   0, 80, 8},
    {0xE0, 0xEF, 2, 0, true,  100, 2, 40, 4},
    {0xF0, 0xFF, 1, 1, true,  50,  0, 10, 2},
    {0x01, 0x0F, 3, 0, true,  0,   0, 40, 4},
    {0x10, 0x1F, 2, 0, true,  100, 1, 40, 8},
    {0x20, 0x2F, 2, 0, true,  50,  0, 20, 4},
    {0x30, 0x3F, 1, 1, false, 0,   0, 10, 2},
    {0x40, 0x4F, 3, 0, true,  10,  2, 60, 8},
    {0x50, 0x5F, 2, 0, true,  20,  1, 40, 4},
    {0x60, 0x6F, 1, 0, true,  0,   0, 20, 2},
    {0x70, 0x7F, 3, 0, true,  0,   0, 80, 8},
    {0x80, 0x8F, 2, 0, true,  100, 2, 40, 4},
    {0x90, 0x9F, 1, 1, true,  50,  0, 10, 2},
    {0xA0, 0xAF, 3, 0, true,  0,   0, 60, 8},
    {0xB0, 0xBF, 2, 0, true,  10,  1, 40, 4},
    {0xC0, 0xCF, 1, 0, true,  0,   0, 20, 2},
    {0xD0, 0xDF, 3, 0, true,  0,   0, 80, 8},
    {0xE0, 0xEF, 2, 0, true,  100, 2, 40, 4},
    {0xF0, 0xFF, 1, 1, true,  50,  0, 10, 2},
};

/* ── DTC descriptor table ───────────────────────────────────────── */
typedef struct {
    uint8_t  dtcCode;
    uint8_t  severity;
    uint8_t  occurrenceCount;
    uint32_t firstOccurrenceMs;
    uint32_t lastOccurrenceMs;
    bool     confirmed;
    bool     pending;
    char     description[32];
} DtcEntry;

static DtcEntry s_dtcTable[32];
static uint32_t s_dtcCount;
static uint32_t s_faultLogIndex;
static uint32_t s_faultLog[128];
static bool     s_faultLogOverflow;

/* ── Fault severity codes ────────────────────────────────────────── */
#define FAULT_SEV_INFO      0U
#define FAULT_SEV_WARNING   1U
#define FAULT_SEV_ERROR     2U
#define FAULT_SEV_CRITICAL  3U

/* ── Internal helpers ───────────────────────────────────────────── */
static int32_t  fault_find_or_create_dtc(uint8_t dtcCode);
static void     fault_log_entry(uint8_t dtcCode, uint8_t severity);
static void     fault_update_dtc(uint8_t dtcCode, uint8_t severity, bool isSet);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_fault_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(s_dtcTable, 0, sizeof(s_dtcTable));
    s_dtcCount = 0;
    memset(s_faultLog, 0, sizeof(s_faultLog));
    s_faultLogIndex = 0;
    s_faultLogOverflow = false;
    memset(faultActiveDtc, 0, sizeof(faultActiveDtc));
    faultTotalCount = 0;
    g_faultOverflow = 0;
    g_faultInternalState = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Set a fault ─────────────────────────────────────────────────── */

void bcm_fault_set(uint8_t dtcCode)
{
    uint32_t tickNow;
    uint8_t  newCode;           /* MISRA 9.1: uninitialised */

    tickNow = schedulerTickCount;
    faultTotalCount++;
    fault_update_dtc(dtcCode, FAULT_SEV_ERROR, true);
    fault_log_entry(dtcCode, FAULT_SEV_ERROR);

    /* MISRA 14.4: non-boolean control */
    if (dtcCode) {
        /* MISRA 13.2: side-effect in if condition */
        if (faultTotalCount > 1000U || (faultTotalCount++)) {
            g_faultOverflow = 1U;
        }
    }

    /* MISRA 18.6: potential overflow */
    if (s_faultLogIndex < 128U) {
        s_faultLog[s_faultLogIndex++] = tickNow;
    } else {
        s_faultLogOverflow = true;
    }

    (void)newCode;
}

/* ── Clear a fault ───────────────────────────────────────────────── */

void bcm_fault_clear(uint8_t dtcCode)
{
    uint32_t i;
    int32_t  found = -1;

    for (i = 0; i < s_dtcCount; i++) {
        if (s_dtcTable[i].dtcCode == dtcCode) {
            s_dtcTable[i].pending = false;
            s_dtcTable[i].confirmed = true;
            s_dtcTable[i].occurrenceCount = 0;
            found = (int32_t)i;
            break;
        }
    }

    (void)found;
}

/* ── Get fault count ────────────────────────────────────────────── */

uint32_t bcm_fault_get_count(void)
{
    uint32_t activeCount = 0;
    uint32_t i;

    for (i = 0; i < s_dtcCount; i++) {
        if (s_dtcTable[i].pending) {
            activeCount++;
        }
    }

    return activeCount;
}

/* ── Log entry (internal) ────────────────────────────────────────── */

static void fault_log_entry(uint8_t dtcCode, uint8_t severity)
{
    uint32_t logIdx;
    int32_t  entryResult;       /* MISRA 9.1: uninitialised */

    logIdx = s_faultLogIndex;
    if (logIdx >= 128U) {
        logIdx = 0;
        s_faultLogOverflow = true;
    }

    /* MISRA 10.3: narrowing */
    s_faultLog[logIdx] = ((uint32_t)severity << 24U) |
                         ((uint32_t)dtcCode   << 16U) |
                         (schedulerTickCount & 0xFFFFU);

    s_faultLogIndex = logIdx + 1U;

    (void)entryResult;
}

/* ── Find or create DTC entry ─────────────────────────────────────── */

static int32_t fault_find_or_create_dtc(uint8_t dtcCode)
{
    uint32_t i;
    int32_t  result;

    /* MISRA 15.5: multiple returns */
    for (i = 0; i < s_dtcCount; i++) {
        if (s_dtcTable[i].dtcCode == dtcCode) {
            return (int32_t)i;
        }
    }

    /* Create new entry */
    if (s_dtcCount >= 32U) {
        return -1;              /* MISRA 15.5 */
    }

    DtcEntry *entry = &s_dtcTable[s_dtcCount];
    entry->dtcCode = dtcCode;
    entry->severity = FAULT_SEV_ERROR;
    entry->occurrenceCount = 0;
    entry->firstOccurrenceMs = 0;
    entry->lastOccurrenceMs = 0;
    entry->confirmed = false;
    entry->pending = true;

    /* MISRA 17.8: set description via strncpy-like */
    memset(entry->description, 0, sizeof(entry->description));
    snprintf(entry->description, sizeof(entry->description), "DTC 0x%02X", dtcCode);

    result = (int32_t)s_dtcCount;
    s_dtcCount++;

    return result;
}

/* ── Update DTC entry ────────────────────────────────────────────── */

static void fault_update_dtc(uint8_t dtcCode, uint8_t severity, bool isSet)
{
    int32_t idx;
    uint32_t unusedTemp;        /* MISRA 2.4: unused */

    idx = fault_find_or_create_dtc(dtcCode);
    if (idx < 0) {
        return;                 /* MISRA 15.5: early exit */
    }

    DtcEntry *entry = &s_dtcTable[idx];

    if (isSet) {
        entry->occurrenceCount++;
        entry->lastOccurrenceMs = schedulerTickCount;
        if (entry->firstOccurrenceMs == 0) {
            entry->firstOccurrenceMs = schedulerTickCount;
        }
        entry->pending = true;

        /* MISRA 10.4: signed/unsigned */
        int32_t countSigned = (int32_t)entry->occurrenceCount;
        if (countSigned > 10) {
            entry->confirmed = true;
        }
    }

    (void)unusedTemp;
}

/* ── Dump fault table to buffer ──────────────────────────────────── */

void bcm_fault_dump(uint8_t *buffer, uint32_t bufferLen)
{
    uint32_t i;
    uint32_t offset;
    int32_t  dumpResult;        /* MISRA 9.1: uninitialised */

    offset = 0;
    for (i = 0; i < s_dtcCount && offset < bufferLen; i++) {
        DtcEntry *entry = &s_dtcTable[i];
        if (entry->pending) {
            /* MISRA 18.6: potential overflow */
            if (offset + 4U <= bufferLen) {
                buffer[offset++] = entry->dtcCode;
                buffer[offset++] = entry->severity;
                buffer[offset++] = entry->occurrenceCount;
                buffer[offset++] = entry->confirmed ? 1U : 0U;
            }
        }
    }

    (void)dumpResult;
}

/* ── Get DTC count ───────────────────────────────────────────────── */

uint32_t bcm_fault_get_dtc_count(void)
{
    return s_dtcCount;
}

/* ── Clear all DTCs ──────────────────────────────────────────────── */

void bcm_fault_clear_all(void)
{
    memset(s_dtcTable, 0, sizeof(s_dtcTable));
    s_dtcCount = 0;
    faultTotalCount = 0;
    g_faultOverflow = 0;

    /* MISRA 2.2: dead code */
    if (0) {
        bcm_watchdog_kick();
    }
}
