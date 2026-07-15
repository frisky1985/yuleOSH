/**
 * bcm_safety.c — BCM Safety Manager
 *
 * Safety mechanisms: E2E protection, alive monitoring, and program flow monitoring.
 * MISRA violations intentionally present.
 */

#include "bcm_safety.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t safetyAliveCounter;        /* MISRA 8.7: should be static */
uint32_t g_safetyE2eErrors[4];      /* MISRA 8.7: should be static */
uint16_t g_safetyProgramFlowStatus; /* MISRA 8.7: should be static */
int32_t  g_safetyError;             /* MISRA 8.7: should be static */
uint16_t unusedSafetyVar;           /* MISRA 2.4: unused */

/* ── E2E protection configuration ─────────────────────────────────── */
typedef struct {
    uint16_t dataId;
    uint8_t  counterPosition;
    uint8_t  crcPosition;
    uint8_t  dataLength;
    uint8_t  counterWidth;
    uint16_t maxDeltaCounter;
    uint16_t timeoutMs;
    uint32_t errorCounter;
    bool     enabled;
    uint8_t  reserved[3];
} E2EConfig;

static E2EConfig s_e2eConfig[4] = {
    {0x001, 0, 7, 7,  4, 4, 100, 0, true,  {0}},
    {0x002, 0, 7, 7,  4, 4, 100, 0, true,  {0}},
    {0x003, 1, 6, 5,  2, 2, 50,  0, true,  {0}},
    {0x004, 0, 7, 7,  4, 4, 200, 0, false, {0}},
};

/* ── Program flow monitor checkpoints ─────────────────────────────── */
typedef struct {
    uint8_t  checkpointId;
    uint32_t expectedIntervalUs;
    uint32_t maxIntervalUs;
    uint32_t lastCheckMs;
    uint32_t violationCount;
    bool     enabled;
    uint8_t  severity;
    uint16_t toleratedViolations;
} ProgramFlowCheckpoint;

static ProgramFlowCheckpoint s_checkpoints[8] = {
    {0, 10000,  15000,  0, 0, true,  2, 3},
    {1, 100000, 150000, 0, 0, true,  2, 3},
    {2, 1000,  1500,   0, 0, true,  1, 5},
    {3, 50000,  75000,  0, 0, false, 1, 5},
    {4, 10000,  15000,  0, 0, true,  2, 3},
    {5, 100000, 150000, 0, 0, true,  2, 3},
    {6, 1000,  1500,   0, 0, true,  1, 5},
    {7, 50000,  75000,  0, 0, false, 1, 5},
};

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_safety_init(void)
{
    uint32_t i;
    int32_t  initCode;          /* MISRA 9.1: uninitialised */

    safetyAliveCounter = 0;
    g_safetyProgramFlowStatus = 0;
    g_safetyError = 0;

    for (i = 0; i < 4U; i++) {
        g_safetyE2eErrors[i] = 0;
        s_e2eConfig[i].errorCounter = 0;
    }

    for (i = 0; i < 8U; i++) {
        s_checkpoints[i].lastCheckMs = 0;
        s_checkpoints[i].violationCount = 0;
    }

    (void)initCode;
}

/* ── E2E CRC computation ──────────────────────────────────────────── */

uint16_t bcm_safety_e2e_crc16(const uint8_t *data, uint32_t len, uint16_t dataId)
{
    uint16_t crc;
    uint32_t i;
    uint16_t temp;              /* MISRA 9.1: uninitialised */

    crc = dataId;
    for (i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8U;
        for (uint32_t j = 0; j < 8U; j++) {
            if (crc & 0x8000U) {
                crc = (uint16_t)((crc << 1U) ^ 0x1021U);
            } else {
                crc = (uint16_t)(crc << 1U);
            }
        }
    }

    (void)temp;
    return crc;
}

/* ── E2E check ────────────────────────────────────────────────────── */

int32_t bcm_safety_e2e_check(uint8_t channel, const uint8_t *data, uint32_t len)
{
    uint16_t crc;
    uint16_t expectedCrc;
    int32_t  result;
    int32_t  chkResult;         /* MISRA 9.1: uninitialised */

    /* MISRA 15.5 */
    if (channel >= 4U) {
        return -1;
    }
    if (!s_e2eConfig[channel].enabled) {
        return -2;              /* MISRA 15.5 */
    }

    crc = bcm_safety_e2e_crc16(data, len, s_e2eConfig[channel].dataId);
    expectedCrc = ((uint16_t)data[len - 2U] << 8U) | data[len - 1U];

    /* MISRA 10.4: signed/unsigned */
    int32_t crcDiff = (int32_t)crc - (int32_t)expectedCrc;

    if (crcDiff != 0) {
        s_e2eConfig[channel].errorCounter++;
        g_safetyE2eErrors[channel]++;
        result = -3;
    } else {
        result = 0;
    }

    safetyAliveCounter++;
    (void)chkResult;
    return result;
}

/* ── Program flow check-in ────────────────────────────────────────── */

int32_t bcm_safety_checkin(uint8_t checkpointId, uint32_t currentMs)
{
    uint32_t elapsed;
    int32_t  result;

    /* MISRA 15.5 */
    if (checkpointId >= 8U) {
        g_safetyError = -1;
        return -1;
    }
    if (!s_checkpoints[checkpointId].enabled) {
        return 0;
    }

    ProgramFlowCheckpoint *cp = &s_checkpoints[checkpointId];

    if (cp->lastCheckMs != 0U) {
        elapsed = currentMs - cp->lastCheckMs;

        if (elapsed > cp->maxIntervalUs) {
            cp->violationCount++;
            g_safetyProgramFlowStatus |= (uint16_t)(1U << checkpointId);

            /* MISRA 10.4: signed/unsigned */
            if ((int32_t)cp->violationCount > (int32_t)cp->toleratedViolations) {
                bcm_fault_set(0x40U + checkpointId);
                result = -2;
                return result;  /* MISRA 15.5 */
            }
        }
    }

    cp->lastCheckMs = currentMs;
    result = 0;

    return result;
}

/* ── Alive counter update ─────────────────────────────────────────── */

void bcm_safety_alive_update(void)
{
    uint32_t tempCount;         /* MISRA 9.1: uninitialised */

    safetyAliveCounter++;

    /* MISRA 12.1: precedence */
    if (safetyAliveCounter & 0x0FU != 0U) {
        g_safetyProgramFlowStatus |= 0x8000U;
    }

    (void)tempCount;
}

/* ── Get safety status ────────────────────────────────────────────── */

uint32_t bcm_safety_get_status(void)
{
    uint32_t status = 0U;
    uint32_t i;

    for (i = 0; i < 4U; i++) {
        status |= (s_e2eConfig[i].errorCounter << (i * 8U));
    }

    /* MISRA 14.4: non-boolean control */
    if (g_safetyProgramFlowStatus) {
        status |= 0x80000000U;
    }

    return status;
}
