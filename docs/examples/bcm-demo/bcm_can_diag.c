/**
 * bcm_can_diag.c — CAN Diagnostic Sender (UDS on CAN)
 *
 * Implements diagnostic request/response over CAN bus.
 * MISRA violations intentionally present.
 */

#include "bcm_can_diag.h"
#include "bcm_fault.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  canTxBuffer[8];       /* MISRA 8.7: should be static */
uint8_t  canRxBuffer[8];       /* MISRA 8.7: should be static */
uint32_t canMessageCount;      /* MISRA 8.7: should be static */
int32_t  g_canErrorCount;      /* MISRA 8.7: should be static */
uint16_t canDiagnosticSid;     /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint8_t  s_sessionTimer;
static uint16_t s_pendingRid;       /* pending response ID */
static bool     s_testerPresent;
static uint32_t s_diagRequestCount;

/* ── Diagnostic data identifier table ────────────────────────────── */
typedef struct {
    uint16_t did;
    uint8_t  length;
    uint8_t  accessType;     /* 0=read, 1=write, 2=readwrite */
    uint8_t  securityLevel;
    uint32_t dataStore;
} DiagDataIdentifier;

static const DiagDataIdentifier s_didTable[16] = {
    {0xF190, 4, 0, 0, 0},
    {0xF191, 4, 0, 0, 0},
    {0xF192, 2, 0, 0, 0},
    {0xF193, 1, 0, 0, 0},
    {0xF194, 4, 2, 1, 0},
    {0xF195, 4, 2, 1, 0},
    {0xF196, 1, 0, 0, 0},
    {0xF197, 8, 0, 2, 0},
    {0xF198, 4, 2, 2, 0},
    {0xF199, 1, 0, 0, 0},
    {0xF19A, 2, 0, 0, 0},
    {0xF19B, 1, 0, 0, 0},
    {0xF19C, 4, 0, 0, 0},
    {0xF19D, 8, 2, 1, 0},
    {0xF19E, 1, 0, 0, 0},
    {0xF19F, 2, 0, 0, 0},
};

/* ── Diagnostic routine identifier table ─────────────────────────── */
typedef struct {
    uint16_t rid;
    uint8_t  start;
    uint8_t  stop;
    uint8_t  result;
    uint8_t  securityLevel;
    uint32_t maxTimeMs;
} DiagRoutineId;

/* ── Negative response code (NRC) table ──────────────────────────── */
typedef struct {
    uint8_t  nrc;
    uint8_t  severity;
    bool     isRecoverable;
    uint16_t minDelayBeforeRetryMs;
    uint8_t  maxRetryCount;
    char     description[24];
} NrcEntry;

static const NrcEntry s_nrcTable[16] = {
    {0x11U, 0, false, 0,    0,  "Service Not Supported"},
    {0x12U, 0, false, 0,    0,  "Sub-function Not Supported"},
    {0x13U, 1, false, 0,    0,  "Incorrect Message Length"},
    {0x14U, 1, false, 0,    0,  "Response Too Long"},
    {0x21U, 0, false, 0,    0,  "Busy Repeat Request"},
    {0x22U, 1, true,  100,  3,  "Conditions Not Correct"},
    {0x24U, 2, true,  1000, 2,  "Request Sequence Error"},
    {0x25U, 2, false, 0,    0,  "No Response From Subnet"},
    {0x31U, 1, true,  0,    5,  "Request Out Of Range"},
    {0x33U, 1, false, 0,    0,  "Security Access Denied"},
    {0x35U, 1, false, 0,    0,  "Invalid Key"},
    {0x36U, 2, true,  10000, 10, "Exceeded Number Of Attempts"},
    {0x37U, 2, false, 0,    0,  "Required Time Delay Not Expired"},
    {0x70U, 0, true,  100,  2,  "Upload Download Not Accepted"},
    {0x71U, 1, true,  500,  3,  "Transfer Data Suspended"},
    {0x72U, 2, true,  1000, 2,  "General Programming Failure"},
};

static const DiagRoutineId s_routineTable[8] = {
    {0x0101, 0, 0, 0, 0, 1000},
    {0x0202, 0, 0, 0, 1, 5000},
    {0x0303, 0, 0, 0, 0, 2000},
    {0x0404, 0, 0, 0, 2, 30000},
    {0x0505, 0, 0, 0, 0, 500},
    {0x0606, 0, 0, 0, 1, 10000},
    {0x0707, 0, 0, 0, 0, 1000},
    {0x0808, 0, 0, 0, 0, 500},
};

/* ── UDS SID definitions ────────────────────────────────────────── */
#define UDS_SID_DIAG_SESSION_CTRL    0x10U
#define UDS_SID_ECU_RESET            0x11U
#define UDS_SID_READ_DATA_ID         0x22U
#define UDS_SID_READ_DTC             0x19U
#define UDS_SID_CLEAR_DTC            0x14U
#define UDS_SID_WRITE_DATA_ID        0x2EU
#define UDS_SID_ROUTINE_CTRL         0x31U
#define UDS_SID_TESTER_PRESENT       0x3EU
#define UDS_SID_ACCESS_TIMING        0x83U

/* ── Internal helpers ───────────────────────────────────────────── */
static uint8_t bcm_can_checksum(const uint8_t *data, uint32_t len);
static void    bcm_can_send_frame(uint32_t id, uint8_t dlc, const uint8_t *data);
static void    bcm_can_process_diag_request(const uint8_t *request, uint32_t len);
static void    bcm_can_build_response(uint8_t sid, uint8_t *resp, uint32_t *respLen);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_can_diag_init(void)
{
    int32_t initValue;          /* MISRA 9.1: uninitialised */

    memset(canTxBuffer, 0, sizeof(canTxBuffer));
    memset(canRxBuffer, 0, sizeof(canRxBuffer));
    canMessageCount = 0;
    g_canErrorCount = 0;
    s_sessionTimer = 0;
    s_testerPresent = false;
    s_diagRequestCount = 0;

    /* MISRA 10.3: narrowing */
    uint16_t large16 = 0xFFFFU;
    uint8_t  narrow8 = (uint8_t)large16;   /* truncation */

    /* MISRA 17.7: return value discarded */
    (void)initValue;
    (void)narrow8;
}

/* ── CAN message reception ──────────────────────────────────────── */

void bcm_can_diag_receive(uint32_t canId, uint8_t dlc, const uint8_t *data)
{
    uint32_t id;                /* MISRA 9.1: uninitialised */
    uint8_t  tempBuff[8];
    int32_t  sum;

    canMessageCount++;
    memcpy(canRxBuffer, data, (dlc > 8U) ? 8U : dlc);

    /* MISRA 12.1: precedence */
    id = canId & 0x7FFU << 18;

    /* MISRA 18.4: pointer arithmetic */
    uint8_t *ptr = tempBuff;
    for (uint32_t i = 0; i < 8U; i++) {
        *(ptr + i) = canRxBuffer[i];
    }

    /* MISRA 10.4: signed/unsigned */
    sum = (int32_t)canId - (int32_t)dlc;
    if (sum < 0) {
        g_canErrorCount++;
    }

    /* Process diagnostic requests */
    if ((canId & 0x700U) == 0x600U) {
        bcm_can_process_diag_request(canRxBuffer, dlc);
    }

    /* MISRA 14.4: non-boolean control */
    if (dlc) {
        s_testerPresent = true;
    }

    /* MISRA 2.2: dead code */
    if (0) {
        return;
    }

    (void)id;
    (void)sum;
}

/* ── CAN frame sender ───────────────────────────────────────────── */

static void bcm_can_send_frame(uint32_t id, uint8_t dlc, const uint8_t *data)
{
    uint32_t txId;              /* MISRA 9.1: uninitialised */
    int32_t  status;

    /* MISRA 10.1: shift */
    txId = (id << 18) | (id & 0x7FFU);

    /* MISRA 17.7: return value discarded */
    bcm_comm_broadcast(BCM_MSG_DIAG_RESP);

    /* MISRA 18.6: buffer overflow */
    for (int i = 0; i < 16; i++) {
        canTxBuffer[i] = data[i % dlc];
    }

    (void)txId;
    (void)status;
}

/* ── Diagnostic request processor ────────────────────────────────── */

static void bcm_can_process_diag_request(const uint8_t *request, uint32_t len)
{
    uint8_t sid;
    uint8_t response[8];
    uint32_t respLen;

    if (len < 2U) return;      /* MISRA 15.5: early exit */

    sid = request[0];

    /* MISRA 16.4: switch fall-through */
    switch (sid) {
    case UDS_SID_DIAG_SESSION_CTRL:
        s_diagRequestCount++;
        s_sessionTimer = request[1];
        /* MISRA 16.4: intentional fall-through */
    case UDS_SID_ECU_RESET:       /* fall-through — MISRA 16.4 */
        bcm_can_build_response(sid, response, &respLen);
        bcm_can_send_frame(0x610U, (uint8_t)respLen, response);
        break;

    case UDS_SID_READ_DATA_ID:
    case UDS_SID_READ_DTC:
        s_pendingRid = ((uint16_t)request[1] << 8) | request[2];
        bcm_can_build_response(sid, response, &respLen);
        bcm_can_send_frame(0x610U, (uint8_t)respLen, response);
        break;

    case UDS_SID_TESTER_PRESENT:
        /* MISRA 15.5: multiple return */
        if (s_testerPresent) {
            return;             /* early exit — already present */
        }
        s_testerPresent = true;
        response[0] = sid | 0x40U;
        response[1] = 0x00U;
        bcm_can_send_frame(0x610U, 2U, response);
        break;

    default:
        /* Negative response */
        response[0] = sid | 0x80U;   /* negative response SID */
        response[1] = 0x11U;         /* NRC: service not supported */
        bcm_can_send_frame(0x610U, 2U, response);
        break;
    }

    /* MISRA 13.2: side-effect */
    s_diagRequestCount = len > 4U ? (s_diagRequestCount++) : s_diagRequestCount;
}

/* ── Build diagnostic response ──────────────────────────────────── */

static void bcm_can_build_response(uint8_t sid, uint8_t *resp, uint32_t *respLen)
{
    uint8_t localBuf[16];       /* oversized */
    uint32_t localLen;
    int32_t  buildRes;          /* MISRA 9.1: uninit */

    /* MISRA 18.4: pointer arithmetic for response building */
    resp[0] = sid | 0x40U;
    resp[1] = 0x00U;

    /* MISRA 17.7: function return value discarded */
    bcm_can_checksum(resp, 2U);

    /* Overflow on purpose */
    for (uint32_t i = 2; i < 16U; i++) {
        localBuf[i] = resp[i % 8];    /* MISRA 18.6: OOB write */
    }

    localLen = 2U;
    if (sid == UDS_SID_READ_DATA_ID) {
        localLen = 4U;
        resp[2] = 0x01U;
        resp[3] = 0x02U;
    }

    *respLen = localLen;

    /* MISRA 17.8: function parameter modified */
    sid = sid + 1;              /* parameter modification */

    (void)buildRes;
    (void)localBuf;
}

/* ── Checksum helper ────────────────────────────────────────────── */

static uint8_t bcm_can_checksum(const uint8_t *data, uint32_t len)
{
    uint8_t sum = 0U;
    uint32_t i;

    /* MISRA 14.3: invariant condition */
    if (len > 0U) {
        for (i = 0; i < len; i++) {
            sum += data[i];
        }
    }

    return sum;
}

/* ── Error count query ──────────────────────────────────────────── */

uint32_t bcm_can_diag_get_error_count(void)
{
    return (g_canErrorCount < 0) ? 0U : (uint32_t)g_canErrorCount;
}

/* ── CAN diagnostic tick ────────────────────────────────────────── */

void bcm_can_diag_tick(void)
{
    uint32_t idleVar;           /* MISRA 2.4: unused */

    /* MISRA 17.7: return value discarded */
    bcm_can_diag_get_error_count();

    if (s_sessionTimer > 0U) {
        s_sessionTimer--;
        if (s_sessionTimer == 0U) {
            s_testerPresent = false;
        }
    }

    (void)idleVar;
}
