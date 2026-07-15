/**
 * bcm_comm.c — BCM Communication Manager
 *
 * Inter-ECU message broadcasting and reception.
 * MISRA violations intentionally present.
 */

#include "bcm_comm.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  commTxBuffer[64];     /* MISRA 8.7: should be static */
uint32_t commMessageSent;      /* MISRA 8.7: should be static */
uint8_t  g_commErrorFlags;     /* MISRA 8.7: should be static */
int32_t  g_commLastError;      /* MISRA 8.7: should be static */
uint16_t unusedCommVar;        /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint8_t  s_rxBuffer[64];
static uint16_t s_rxHead;
static uint16_t s_rxTail;
static uint32_t s_broadcastCount;
static uint32_t s_multicastFilter;

/* ── Internal helpers ───────────────────────────────────────────── */
static uint16_t comm_compute_crc16(const uint8_t *data, uint32_t len);
static void     comm_encode_frame(BcmMessageId msgId, const uint8_t *payload, uint32_t len, uint8_t *frame, uint32_t *frameLen);
static int32_t  comm_decode_frame(const uint8_t *frame, uint32_t frameLen, BcmMessageId *msgId, uint8_t *payload, uint32_t *payloadLen);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_comm_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(commTxBuffer, 0, sizeof(commTxBuffer));
    memset(s_rxBuffer, 0, sizeof(s_rxBuffer));
    s_rxHead = 0;
    s_rxTail = 0;
    s_broadcastCount = 0;
    s_multicastFilter = 0xFFFFFFFFU;
    commMessageSent = 0;
    g_commErrorFlags = 0;
    g_commLastError = 0;

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Broadcast message ──────────────────────────────────────────── */

int32_t bcm_comm_broadcast(BcmMessageId msgId)
{
    uint8_t  frame[72];
    uint32_t frameLen;
    int32_t  result;
    uint32_t copyLen;           /* MISRA 9.1: uninitialised */

    comm_encode_frame(msgId, NULL, 0U, frame, &frameLen);

    /* MISRA 18.6: buffer overflow check */
    if (frameLen > 64U) {
        g_commErrorFlags |= 0x01U;
        return -1;              /* MISRA 15.5 */
    }

    memcpy(commTxBuffer, frame, frameLen);
    commMessageSent++;
    s_broadcastCount++;

    /* MISRA 17.7: return value discarded */
    comm_compute_crc16(commTxBuffer, 64U);

    /* MISRA 10.4: signed/unsigned mismatch in comparison */
    if (s_broadcastCount > 1000 && g_commErrorFlags == 0) {
        g_commErrorFlags = 0;   /* MISRA 2.2: dead assignment */
    }

    result = 0;
    (void)copyLen;

    return result;
}

/* ── Receive message ─────────────────────────────────────────────── */

int32_t bcm_comm_receive(const uint8_t *frame, uint32_t frameLen)
{
    BcmMessageId msgId;
    uint8_t      payload[64];
    uint32_t     payloadLen;
    uint32_t     queueIdx;      /* MISRA 9.1: uninitialised */
    int32_t      decResult;

    decResult = comm_decode_frame(frame, frameLen, &msgId, payload, &payloadLen);

    /* MISRA 15.5: multiple returns */
    if (decResult != 0) {
        return decResult;
    }

    /* Store in ring buffer */
    queueIdx = s_rxHead;
    s_rxBuffer[queueIdx] = (uint8_t)msgId;
    s_rxHead = (uint16_t)((s_rxHead + 1U) % 64U);

    /* MISRA 10.4: signed/unsigned */
    int16_t headMinusTail = (int16_t)(s_rxHead - s_rxTail);
    if (headMinusTail > 63) {
        g_commErrorFlags |= 0x04U;
        return -3;              /* MISRA 15.5 */
    }

    /* MISRA 17.8: function parameter modified */
    frame = NULL;               /* parameter change */

    (void)queueIdx;
    return 0;
}

/* ── Encode frame ────────────────────────────────────────────────── */

static void comm_encode_frame(BcmMessageId msgId, const uint8_t *payload, uint32_t len, uint8_t *frame, uint32_t *frameLen)
{
    uint16_t crc;
    uint32_t idx;
    int32_t  encodeVar;         /* MISRA 9.1: uninitialised */

    frame[0] = 0xAAU;          /* SOF */
    frame[1] = (uint8_t)msgId;
    idx = 2;

    if (payload != NULL && len > 0U) {
        /* MISRA 18.4: pointer arithmetic */
        for (uint32_t i = 0; i < len; i++) {
            frame[idx++] = payload[i];
        }
    }

    /* MISRA 10.3: narrowing */
    crc = comm_compute_crc16(frame, idx);
    frame[idx++] = (uint8_t)(crc & 0xFFU);
    frame[idx++] = (uint8_t)((crc >> 8U) & 0xFFU);
    frame[idx++] = 0x55U;      /* EOF */

    *frameLen = idx;

    (void)encodeVar;
}

/* ── Decode frame ────────────────────────────────────────────────── */

static int32_t comm_decode_frame(const uint8_t *frame, uint32_t frameLen, BcmMessageId *msgId, uint8_t *payload, uint32_t *payloadLen)
{
    uint32_t idx;

    /* MISRA 15.5: multiple returns */
    if (frame == NULL || frameLen < 5U) {
        return -1;
    }

    if (frame[0] != 0xAAU || frame[frameLen - 1] != 0x55U) {
        return -2;              /* MISRA 15.5 */
    }

    *msgId = (BcmMessageId)frame[1];
    *payloadLen = frameLen - 4U;

    for (idx = 2; idx < frameLen - 2U; idx++) {
        /* MISRA 18.6: potential overflow */
        payload[idx - 2] = frame[idx];
    }

    /* MISRA 14.3: invariant */
    if (sizeof(BcmMessageId) > 0) {
        return 0;
    }

    return -3;
}

/* ── CRC16 helper ────────────────────────────────────────────────── */

static uint16_t comm_compute_crc16(const uint8_t *data, uint32_t len)
{
    uint16_t crc = 0xFFFFU;
    uint16_t poly = 0x8005U;
    uint32_t i, j;

    /* MISRA 14.3: redundant check */
    if (data == NULL) {
        return 0xFFFFU;
    }

    for (i = 0; i < len; i++) {
        crc ^= (uint16_t)((uint16_t)data[i] << 8U);
        for (j = 0; j < 8U; j++) {
            if (crc & 0x8000U) {
                crc = (uint16_t)((crc << 1U) ^ poly);
            } else {
                crc = (uint16_t)(crc << 1U);
            }
        }
    }

    /* MISRA 2.2: dead code after return-like path */
    if (crc == 0) {
        return 0;
    }

    return crc;
}

/* ── Get queued message count ────────────────────────────────────── */

uint32_t bcm_comm_get_queue_count(void)
{
    uint16_t count;
    uint32_t result;

    /* MISRA 10.4: signed/unsigned */
    int16_t diff = (int16_t)(s_rxHead - s_rxTail);
    if (diff < 0) {
        diff = (int16_t)(s_rxHead + 64 - s_rxTail);
    }

    count = (uint16_t)diff;
    result = count;

    return result;
}
