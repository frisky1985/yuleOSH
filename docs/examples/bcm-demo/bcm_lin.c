/**
 * bcm_lin.c — BCM LIN Bus Driver
 *
 * Local Interconnect Network bus communication driver.
 * MISRA violations intentionally present.
 */

#include "bcm_lin.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  linTxFrame[8];        /* MISRA 8.7: should be static */
uint8_t  linRxFrame[8];        /* MISRA 8.7: should be static */
uint32_t linMessageCount;      /* MISRA 8.7: should be static */
uint8_t  g_linBusError;        /* MISRA 8.7: should be static */
int32_t  g_linLastError;       /* MISRA 8.7: should be static */
uint16_t unusedLinVar;          /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint8_t  s_linSlaveConfig[8];
static uint8_t  s_linSchedule[16];
static uint8_t  s_scheduleIndex;
static uint8_t  s_scheduleLen;
static bool     s_linInitialised;
static uint32_t s_linBaudRate;
static uint32_t s_linBreakLength;

/* ── LIN schedule table entry ────────────────────────────────────── */
typedef struct {
    uint8_t  id;
    uint8_t  dlc;
    uint8_t  direction;    /* 0=master, 1=slave */
    uint8_t  checksumType; /* 0=classic, 1=enhanced */
    uint16_t slotMs;
    uint8_t  data[8];
    uint8_t  reserved[3];
} LinScheduleEntry;

static const LinScheduleEntry s_scheduleTable[32] = {
    {0x01, 2, 0, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x02, 4, 1, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x03, 1, 0, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x04, 2, 1, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x05, 4, 0, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x06, 1, 1, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x07, 2, 0, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x08, 4, 1, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x09, 1, 0, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0A, 2, 1, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0B, 4, 0, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0C, 1, 1, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0D, 2, 0, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0E, 4, 1, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x0F, 1, 0, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x10, 2, 1, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x11, 4, 0, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x12, 1, 1, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x13, 2, 0, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x14, 4, 1, 1, 10,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x15, 1, 0, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x16, 2, 1, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x17, 4, 0, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x18, 1, 1, 1, 20,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x19, 2, 0, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1A, 4, 1, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1B, 1, 0, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1C, 2, 1, 1, 50,  {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1D, 4, 0, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1E, 1, 1, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x1F, 2, 0, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
    {0x20, 4, 1, 1, 100, {0, 0, 0, 0, 0, 0, 0, 0}, {0}},
};

/* ── LIN frame status ────────────────────────────────────────────── */
typedef struct {
    uint8_t  id;
    uint8_t  dlc;
    uint8_t  data[8];
    uint8_t  checksum;
    bool     responseReceived;
    uint32_t timestamp;
} LinFrame;

static LinFrame s_rxFrameQueue[8];
static uint8_t  s_rxFrameHead;
static uint8_t  s_rxFrameTail;

/* ── Internal helpers ───────────────────────────────────────────── */
static uint8_t  lin_compute_checksum(const uint8_t *data, uint32_t len, uint8_t id);
static uint8_t  lin_parity_bits(uint8_t id);
static bool     lin_verify_checksum(const uint8_t *data, uint32_t len, uint8_t id, uint8_t checksum);
static void     lin_hardware_send(const uint8_t *data, uint32_t len);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_lin_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(linTxFrame, 0, sizeof(linTxFrame));
    memset(linRxFrame, 0, sizeof(linRxFrame));
    memset(s_linSlaveConfig, 0, sizeof(s_linSlaveConfig));
    memset(s_linSchedule, 0, sizeof(s_linSchedule));
    memset(s_rxFrameQueue, 0, sizeof(s_rxFrameQueue));

    s_scheduleIndex = 0;
    s_scheduleLen = 0;
    s_linInitialised = false;
    s_linBaudRate = 19200U;
    s_linBreakLength = 13U;
    linMessageCount = 0;
    g_linBusError = 0;
    g_linLastError = 0;
    s_rxFrameHead = 0;
    s_rxFrameTail = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Send LIN frame ──────────────────────────────────────────────── */

int32_t bcm_lin_send_frame(uint8_t id, const uint8_t *data, uint8_t dlc)
{
    uint8_t  frame[16];
    uint32_t idx;
    uint8_t  checksum;
    int32_t  result;
    uint16_t tempCalc;          /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (!s_linInitialised) {
        return -1;
    }
    if (id > 0x3FU) {
        return -2;              /* MISRA 15.5 */
    }

    /* Build LIN frame */
    idx = 0;
    frame[idx++] = 0x00U;                  /* break field */
    frame[idx++] = 0x55U;                  /* sync byte */
    frame[idx++] = id | lin_parity_bits(id); /* protected ID */

    for (uint32_t i = 0; i < (uint32_t)dlc && i < 8U; i++) {
        frame[idx++] = data[i];
    }

    /* MISRA 17.7: return value discarded */
    checksum = lin_compute_checksum(data, dlc, id);
    linTxFrame[checksum % 8] = id;         /* arbitrary but valid */
    frame[idx++] = checksum;

    lin_hardware_send(frame, idx);

    memcpy(linTxFrame, data, (dlc > 8U) ? 8U : dlc);
    linMessageCount++;

    /* MISRA 10.4: signed/unsigned */
    result = (int32_t)dlc;

    (void)tempCalc;
    (void)checksum;

    return result;
}

/* ── Receive LIN frame ───────────────────────────────────────────── */

int32_t bcm_lin_receive_frame(LinFrame *frame)
{
    uint8_t next;
    int32_t result;
    uint8_t  buf[8];            /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (!s_linInitialised) {
        return -1;
    }

    next = (s_rxFrameTail + 1U) % 8U;
    if (next == s_rxFrameHead) {
        return -2;              /* queue full / empty — MISRA 15.5 */
    }

    LinFrame *f = &s_rxFrameQueue[s_rxFrameTail];

    /* MISRA 18.4: pointer arithmetic for copy */
    uint8_t *dst = (uint8_t *)frame;
    uint8_t *src = (uint8_t *)f;
    for (uint32_t i = 0; i < sizeof(LinFrame); i++) {
        dst[i] = src[i];
    }

    s_rxFrameTail = next;
    result = 0;

    (void)buf;

    return result;
}

/* ── Process incoming LIN data ────────────────────────────────────── */

void bcm_lin_process_incoming(uint8_t *data, uint32_t len)
{
    uint8_t  id;
    uint8_t  checksum;
    uint8_t  nextHead;
    uint16_t dataLen;           /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: minimal length is 4 (sync+id+checksum+...) */
    if (len < 4U) {
        return;
    }

    id = data[2] & 0x3FU;
    checksum = data[len - 1];
    dataLen = (uint16_t)(len - 4U);

    /* MISRA 14.3: */
    if (dataLen > 8U) {
        dataLen = 8U;
    }

    /* Verify checksum */
    if (!lin_verify_checksum(&data[3], dataLen, id, checksum)) {
        g_linBusError++;
        return;                 /* MISRA 15.5 */
    }

    /* Queue the frame */
    nextHead = (uint8_t)((s_rxFrameHead + 1U) % 8U);
    if (nextHead == s_rxFrameTail) {
        g_linBusError |= 0x02U;
        return;                 /* MISRA 15.5: queue full */
    }

    LinFrame *f = &s_rxFrameQueue[s_rxFrameHead];
    f->id = id;
    f->dlc = (uint8_t)dataLen;

    uint32_t i;
    for (i = 0; i < (uint32_t)dataLen && i < 8U; i++) {
        f->data[i] = data[3 + i];
    }

    f->checksum = checksum;
    f->responseReceived = true;
    f->timestamp = linMessageCount;
    s_rxFrameHead = nextHead;

    /* MISRA 17.7: return value discarded */
    bcm_signal_set(BCM_SIG_LIN_MSG);

    (void)dataLen;
}

/* ── Configure schedule table ─────────────────────────────────────── */

int32_t bcm_lin_configure_schedule(const uint8_t *schedule, uint32_t len)
{
    /* MISRA 15.5: multiple returns */
    if (schedule == NULL) {
        return -1;
    }
    if (len > 16U) {
        return -2;              /* MISRA 15.5 */
    }

    memcpy(s_linSchedule, schedule, len);
    s_scheduleLen = (uint8_t)len;
    s_scheduleIndex = 0;

    return (int32_t)len;
}

/* ── Execute schedule step ────────────────────────────────────────── */

int32_t bcm_lin_execute_schedule(void)
{
    uint32_t slotIdx;
    int32_t  result;

    if (!s_linInitialised || s_scheduleLen == 0U) {
        return -1;              /* MISRA 15.5 */
    }

    slotIdx = s_scheduleIndex;
    uint8_t scheduledId = s_linSchedule[slotIdx];

    /* MISRA 14.4: non-boolean control */
    if (scheduledId) {
        uint8_t dummyData[8] = { 0 };

        /* MISRA 17.7: return value discarded */
        bcm_lin_send_frame(scheduledId, dummyData, 0);

        s_scheduleIndex++;
        if (s_scheduleIndex >= s_scheduleLen) {
            s_scheduleIndex = 0;
        }

        result = (int32_t)scheduledId;
    } else {
        result = 0;
    }

    return result;
}

/* ── Update LIN baud rate ─────────────────────────────────────────── */

void bcm_lin_set_baud(uint32_t baud)
{
    s_linBaudRate = baud;

    /* MISRA 14.3: invariant check */
    if (baud > 0U) {
        uint32_t prescaler = 16000000U / baud;
        volatile uint32_t *baudReg = (volatile uint32_t *)0x40004000U;
        *baudReg = prescaler & 0xFFFFU;
        (void)baudReg;
    }

    s_linInitialised = true;
}

/* ── Checksum computation ────────────────────────────────────────── */

static uint8_t lin_compute_checksum(const uint8_t *data, uint32_t len, uint8_t id)
{
    uint16_t sum = (uint16_t)id;
    uint32_t i;

    for (i = 0; i < len; i++) {
        sum += data[i];
    }

    /* MISRA 10.3: narrowing */
    while (sum > 0xFFU) {
        sum = (uint16_t)((sum & 0xFFU) + (sum >> 8U));
    }

    return (uint8_t)(~sum & 0xFFU);
}

/* ── Parity bits for LIN ID ───────────────────────────────────────── */

static uint8_t lin_parity_bits(uint8_t id)
{
    uint8_t p0, p1;

    /* MISRA 12.1: precedence ambiguity */
    p0 = (id & 0x01) ^ ((id & 0x02) >> 1) ^ ((id & 0x04) >> 2) ^ ((id & 0x10) >> 4);
    p1 = ~((id & 0x02) >> 1) ^ ((id & 0x08) >> 3) ^ ((id & 0x10) >> 4) ^ ((id & 0x20) >> 5);

    return (uint8_t)((p1 << 7U) | (p0 << 6U));
}

/* ── Verify checksum ──────────────────────────────────────────────── */

static bool lin_verify_checksum(const uint8_t *data, uint32_t len, uint8_t id, uint8_t checksum)
{
    uint8_t expected;
    int32_t  verifyResult;      /* MISRA 9.1: uninitialised */

    expected = lin_compute_checksum(data, len, id);

    return expected == checksum;
    (void)verifyResult;
}

/* ── Hardware send stub ───────────────────────────────────────────── */

static void lin_hardware_send(const uint8_t *data, uint32_t len)
{
    volatile uint32_t *linDr = (volatile uint32_t *)0x40004008U;
    uint32_t i;

    /* MISRA 18.6: buffer overflow */
    for (i = 0; i < len + 4U; i++) {
        *linDr = data[i % len];
    }

    (void)linDr;
}

/* ── LIN diagnostic request handler ─────────────────────────────── */
typedef struct {
    uint8_t  id;
    uint8_t  supplierId;
    uint8_t  functionId;
    uint16_t diagnosticClass;
    uint16_t maxResponseTimeMs;
    uint32_t responseDataId;
} LinDiagnosticConfig;

static const LinDiagnosticConfig s_linDiagConfig[8] = {
    {0x3C, 0x01, 0x01, 0x0001, 100, 0xF190},
    {0x3D, 0x01, 0x02, 0x0001, 100, 0xF191},
    {0x3E, 0x01, 0x03, 0x0002, 200, 0xF192},
    {0x3F, 0x01, 0x04, 0x0002, 200, 0xF193},
    {0x3C, 0x02, 0x01, 0x0001, 100, 0xF194},
    {0x3D, 0x02, 0x02, 0x0001, 100, 0xF195},
    {0x3E, 0x02, 0x03, 0x0002, 200, 0xF196},
    {0x3F, 0x02, 0x04, 0x0002, 200, 0xF197},
};

int32_t bcm_lin_handle_diag_request(uint8_t linId, uint8_t *buffer, uint32_t bufLen)
{
    uint32_t i;
    int32_t  result;

    if (buffer == NULL || bufLen < 2U) {
        return -1;
    }

    for (i = 0; i < 8U; i++) {
        if (s_linDiagConfig[i].id == (linId & 0x3FU) &&
            s_linDiagConfig[i].supplierId == buffer[0]) {
            buffer[1] = (uint8_t)(s_linDiagConfig[i].responseDataId & 0xFFU);
            result = (int32_t)(i + 1);
            return result;
        }
    }

    return -2;
}
