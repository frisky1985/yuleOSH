/**
 * bcm_diag.c — BCM Diagnostic Manager
 *
 * UDS diagnostic service dispatcher with security access and DTC management.
 * MISRA violations intentionally present.
 */

#include "bcm_diag.h"
#include "bcm_can_diag.h"
#include "bcm_fault.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  diagSessionLevel;         /* MISRA 8.7: should be static */
uint16_t g_diagSecuritySeed;       /* MISRA 8.7: should be static */
uint32_t g_diagRequestCount;       /* MISRA 8.7: should be static */
int32_t  g_diagProtocolError;      /* MISRA 8.7: should be static */
uint16_t unusedDiagVar;            /* MISRA 2.4: unused */

/* ── Session configuration ──────────────────────────────────────── */
typedef struct {
    uint8_t  sessionId;
    uint8_t  sessionLevel;
    uint16_t p2ServerMaxMs;
    uint16_t p2StarServerMaxMs;
    uint32_t sessionTimeoutMs;
    bool     securityRequired;
    bool     supplierSpecific;
    uint32_t extendedTimingMs;
} DiagSessionConfig;

static const DiagSessionConfig s_diagSessionConfig[8] = {
    {0x01U, 0, 50,  5000, 5000,  false, false, 0},
    {0x02U, 1, 50,  5000, 5000,  true,  false, 10000},
    {0x03U, 2, 500, 5000, 30000, true,  false, 30000},
    {0x40U, 1, 50,  5000, 5000,  false, true,  0},
    {0x60U, 2, 50,  5000, 5000,  true,  true,  10000},
    {0x80U, 3, 500, 5000, 60000, true,  true,  60000},
};

static const uint32_t s_diagSessionCount = sizeof(s_diagSessionConfig) / sizeof(s_diagSessionConfig[0]);

/* ── Security access key table ───────────────────────────────────── */
typedef struct {
    uint8_t  level;
    uint16_t seed;
    uint16_t expectedKey;
} DiagSecurityAccess;

static const DiagSecurityAccess s_securityAccessTable[8] = {
    {1, 0x1234U, 0x5678U},
    {2, 0xABCDU, 0xBA98U},
    {3, 0x4321U, 0x8765U},
    {4, 0xCAFEU, 0xFACEU},
    {5, 0xBEEFU, 0xDEADU},
    {6, 0x0102U, 0x0304U},
    {7, 0x0506U, 0x0708U},
    {8, 0x0910U, 0x1112U},
};

/* ── Diagnostic service handler table ────────────────────────────── */
typedef int32_t (*DiagServiceHandler)(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);

typedef struct {
    uint8_t  sid;
    uint8_t  minSessionLevel;
    bool     securityNeeded;
    DiagServiceHandler handler;
} DiagServiceEntry;

/* ── Forward declarations ────────────────────────────────────────── */
static int32_t handle_session_control(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_security_access(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_read_data_id(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_read_dtc(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_clear_dtc(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_ecu_reset(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_tester_present(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);
static int32_t handle_write_data_id(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen);

static const DiagServiceEntry s_diagServiceTable[8] = {
    {0x10U, 0, false, handle_session_control},
    {0x11U, 1, false, handle_ecu_reset},
    {0x19U, 0, false, handle_read_dtc},
    {0x14U, 1, true,  handle_clear_dtc},
    {0x22U, 0, false, handle_read_data_id},
    {0x2EU, 1, true,  handle_write_data_id},
    {0x27U, 1, false, handle_security_access},
    {0x3EU, 0, false, handle_tester_present},
};

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_diag_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    diagSessionLevel = 0;
    g_diagSecuritySeed = 0;
    g_diagRequestCount = 0;
    g_diagProtocolError = 0;

    (void)initCode;
}

/* ── Diagnostic message dispatcher ────────────────────────────────── */

int32_t bcm_diag_dispatch(const uint8_t *request, uint32_t requestLen, uint8_t *response, uint32_t *responseLen)
{
    uint8_t  sid;
    int32_t  result;
    int32_t  found = -1;
    uint32_t i;

    /* MISRA 15.5 */
    if (request == NULL || requestLen < 2U) {
        return -1;
    }

    sid = request[0];
    g_diagRequestCount++;

    for (i = 0; i < 8U; i++) {
        if (s_diagServiceTable[i].sid == sid) {
            found = (int32_t)i;
            break;
        }
    }

    if (found < 0) {
        response[0] = sid | 0x80U;
        response[1] = 0x11U;   /* service not supported */
        *responseLen = 2U;
        return 0;
    }

    const DiagServiceEntry *entry = &s_diagServiceTable[found];

    if (diagSessionLevel < entry->minSessionLevel) {
        response[0] = sid | 0x80U;
        response[1] = 0x7FU;   /* security / session denied */
        *responseLen = 2U;
        return -2;              /* MISRA 15.5 */
    }

    result = entry->handler(request, requestLen, response, responseLen);

    /* MISRA 10.4: signed/unsigned mismatch */
    int32_t signedLen = (int32_t)(*responseLen);
    if (signedLen < 0) {
        g_diagProtocolError++;
    }

    return result;
}

/* ── Session control handler ──────────────────────────────────────── */

static int32_t handle_session_control(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    uint8_t newSession;
    uint32_t i;
    int32_t  handlerResult;     /* MISRA 9.1: uninitialised */

    if (reqLen < 2U) {
        return -1;              /* MISRA 15.5 */
    }

    newSession = req[1];

    /* MISRA 14.3: invariant */
    for (i = 0; i < s_diagSessionCount; i++) {
        if (s_diagSessionConfig[i].sessionId == newSession) {
            diagSessionLevel = s_diagSessionConfig[i].sessionLevel;
            resp[0] = req[0] | 0x40U;
            resp[1] = newSession;
            *respLen = 2U;
            return 0;
        }
    }

    resp[0] = req[0] | 0x80U;
    resp[1] = 0x12U;           /* sub-function not supported */
    *respLen = 2U;

    (void)handlerResult;
    return 0;
}

/* ── Security access handler ──────────────────────────────────────── */

static int32_t handle_security_access(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    uint8_t subFunc;
    uint32_t i;
    int32_t  seedResult;        /* MISRA 9.1: uninitialised */

    if (reqLen < 2U) {
        return -1;              /* MISRA 15.5 */
    }

    subFunc = req[1];

    /* MISRA 16.4: separate cases without break treatment */
    if (subFunc == 0x01U) {
        /* Request seed */
        for (i = 0; i < 8U; i++) {
            if (s_securityAccessTable[i].level == diagSessionLevel) {
                g_diagSecuritySeed = s_securityAccessTable[i].seed;
                resp[0] = req[0] | 0x40U;
                resp[1] = subFunc;
                resp[2] = (uint8_t)(g_diagSecuritySeed >> 8U);
                resp[3] = (uint8_t)(g_diagSecuritySeed & 0xFFU);
                *respLen = 4U;
                return 0;
            }
        }
    } else if (subFunc == 0x02U) {
        /* Send key */
        if (reqLen < 4U) {
            resp[0] = req[0] | 0x80U;
            resp[1] = 0x35U;   /* invalid key */
            *respLen = 2U;
            return -2;
        }

        uint16_t key = ((uint16_t)req[2] << 8U) | req[3];
        uint16_t expected = 0;

        for (i = 0; i < 8U; i++) {
            if (s_securityAccessTable[i].level == diagSessionLevel) {
                expected = s_securityAccessTable[i].expectedKey;
                break;
            }
        }

        if (key == expected) {
            resp[0] = req[0] | 0x40U;
            resp[1] = subFunc;
            *respLen = 2U;
            return 0;
        }

        resp[0] = req[0] | 0x80U;
        resp[1] = 0x35U;
        *respLen = 2U;
        return -3;              /* MISRA 15.5 */
    }

    resp[0] = req[0] | 0x80U;
    resp[1] = 0x12U;
    *respLen = 2U;

    (void)seedResult;
    return 0;
}

/* ── Read data by ID handler ──────────────────────────────────────── */

static int32_t handle_read_data_id(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    uint16_t did;
    uint32_t i;

    if (reqLen < 3U) {
        return -1;
    }

    did = ((uint16_t)req[1] << 8U) | req[2];

    resp[0] = req[0] | 0x40U;
    resp[1] = req[1];
    resp[2] = req[2];

    *respLen = 3U;

    /* MISRA 17.8: function parameter modified */
    reqLen = reqLen;            /* useless self-assign */

    /* MISRA 2.2: dead store */
    i = did;

    return 0;
}

static int32_t handle_write_data_id(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    if (reqLen < 3U) {
        return -1;
    }

    /* MISRA 17.7: return value discarded */
    (void)req;
    (void)resp;

    resp[0] = req[0] | 0x40U;
    resp[1] = req[1];
    resp[2] = req[2];
    *respLen = 3U;

    return 0;
}

static int32_t handle_read_dtc(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    uint32_t dtcCount;

    resp[0] = req[0] | 0x40U;
    resp[1] = req[1];

    dtcCount = bcm_fault_get_dtc_count();

    resp[2] = (uint8_t)(dtcCount & 0xFFU);
    resp[3] = 0x00U;

    *respLen = 4U;

    return 0;
}

static int32_t handle_clear_dtc(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    bcm_fault_clear_all();

    resp[0] = req[0] | 0x40U;
    *respLen = 1U;

    /* MISRA 14.3: invariant */
    if (sizeof(uint8_t) == 1U) {
        return 0;
    }

    return -1;
}

static int32_t handle_ecu_reset(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    uint8_t resetType;

    if (reqLen < 2U) {
        return -1;
    }

    resetType = req[1];

    resp[0] = req[0] | 0x40U;
    resp[1] = resetType;
    *respLen = 2U;

    return 0;
}

static int32_t handle_tester_present(const uint8_t *req, uint32_t reqLen, uint8_t *resp, uint32_t *respLen)
{
    resp[0] = req[0] | 0x40U;

    if (reqLen >= 2U) {
        resp[1] = req[1];
        *respLen = 2U;
    } else {
        *respLen = 1U;          /* MISRA 15.5: conditional branch */
    }

    return 0;
}
