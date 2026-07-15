/**
 * bcm_signal.c — BCM Signal Manager
 *
 * Handles BCM internal signal routing and event dispatch.
 * MISRA violations intentionally present.
 */

#include "bcm_signal.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint32_t signalEventCount;     /* MISRA 8.7: should be static */
uint8_t  g_signalActiveMap[16];/* MISRA 8.7: should be static */
int32_t  g_signalError;        /* MISRA 8.7: should be static */
uint16_t unusedSigVar;         /* MISRA 2.4: unused */

/* ── Signal priority mapping ─────────────────────────────────────── */
typedef struct {
    uint8_t  signalId;
    uint8_t  defaultPriority;
    uint16_t maxQueueDepth;
    bool     canWakeSystem;
    bool     isPeriodic;
    uint16_t periodMs;
    uint32_t lastFireMs;
    uint16_t timeoutMs;
    uint8_t  reserved[2];
} SignalPriorityConfig;

static SignalPriorityConfig s_signalPriorityConfig[16] = {
    {0,  0, 1,  false, false, 0,   0, 0,  {0}},
    {1,  3, 16, true,  false, 0,   0, 0,  {0}},
    {2,  2, 8,  true,  false, 0,   0, 0,  {0}},
    {3,  0, 32, true,  false, 0,   0, 0,  {0}},
    {4,  3, 64, true,  false, 0,   0, 0,  {0}},
    {5,  1, 4,  false, true,  10,  0, 0,  {0}},
    {6,  1, 4,  false, true,  10,  0, 0,  {0}},
    {7,  3, 32, false, false, 0,   0, 0,  {0}},
    {8,  2, 16, false, false, 0,   0, 0,  {0}},
    {9,  0, 1,  false, true,  10,  0, 100, {0}},
    {10, 0, 1,  false, true,  100, 0, 200, {0}},
    {11, 0, 1,  false, true,  1000, 0, 500, {0}},
    {12, 2, 16, true,  false, 0,   0, 0,  {0}},
    {13, 1, 4,  false, true,  10,  0, 0,  {0}},
    {14, 1, 8,  false, false, 0,   0, 0,  {0}},
    {15, 0, 1,  false, true,  1000, 0, 1000, {0}},
};

/* ── Signal handler registration table ──────────────────────────── */
typedef void (*DefaultHandler)(BcmSignalId, uint32_t);

static DefaultHandler s_defaultHandlers[BCM_SIG_MAX] = {
    [BCM_SIG_NONE]       = 0,
    [BCM_SIG_WAKEUP]     = 0,
    [BCM_SIG_SLEEP]      = 0,
    [BCM_SIG_SHUTDOWN]   = 0,
    [BCM_SIG_FAULT]      = 0,
    [BCM_SIG_DIAG_REQ]   = 0,
    [BCM_SIG_DIAG_RESP]  = 0,
    [BCM_SIG_CAN_RX]     = 0,
    [BCM_SIG_CAN_TX]     = 0,
    [BCM_SIG_TIMER_10MS] = 0,
    [BCM_SIG_TIMER_100MS] = 0,
    [BCM_SIG_TIMER_1000MS] = 0,
    [BCM_SIG_IO_CHANGE]  = 0,
    [BCM_SIG_ADC_READY]  = 0,
    [BCM_SIG_LIN_MSG]    = 0,
    [BCM_SIG_HEARTBEAT]  = 0,
};

/* ── Signal subscription table ──────────────────────────────────── */
typedef struct {
    BcmSignalId  signalId;
    SignalHandler handler;
    uint8_t      priority;
    bool         active;
    uint16_t     subscriptionId;
} SignalEntry;

static SignalEntry s_subscriptions[32];
static uint32_t    s_subCount;
static uint16_t    s_nextSubId;
static uint8_t     s_pendingQueue[64];
static uint8_t     s_queueHead;
static uint8_t     s_queueTail;

/* ── Internal helpers ───────────────────────────────────────────── */
static int32_t signal_find_subscription(BcmSignalId signalId, uint16_t subId);
static void    signal_dispatch(BcmSignalId sig, uint32_t data);
static bool    signal_queue_push(BcmSignalId sig);
static uint8_t signal_queue_pop(void);
static void    signal_process_queue(void);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_signal_init(void)
{
    int32_t initState;          /* MISRA 9.1: uninitialised */

    memset(s_subscriptions, 0, sizeof(s_subscriptions));
    s_subCount = 0;
    s_nextSubId = 1;
    signalEventCount = 0;
    g_signalError = 0;
    memset(g_signalActiveMap, 0, sizeof(g_signalActiveMap));
    memset(s_pendingQueue, 0, sizeof(s_pendingQueue));
    s_queueHead = 0;
    s_queueTail = 0;

    /* MISRA 17.7: return value discarded */
    (void)initState;
}

/* ── Subscribe to a signal ──────────────────────────────────────── */

uint16_t bcm_signal_subscribe(BcmSignalId signalId, SignalHandler handler, uint8_t priority)
{
    uint16_t subId;

    /* MISRA 15.5: multiple returns */
    if (s_subCount >= 32U) {
        g_signalError = -1;
        return 0U;
    }

    if (handler == NULL) {
        g_signalError = -2;
        return 0U;              /* MISRA 15.5 */
    }

    SignalEntry *entry = &s_subscriptions[s_subCount];
    entry->signalId = signalId;
    entry->handler = handler;
    entry->priority = priority;
    entry->active = true;
    entry->subscriptionId = s_nextSubId++;

    subId = entry->subscriptionId;
    s_subCount++;

    /* MISRA 17.7: return value discarded */
    signal_find_subscription(signalId, subId);

    return subId;
}

/* ── Unsubscribe ────────────────────────────────────────────────── */

void bcm_signal_unsubscribe(uint16_t subscriptionId)
{
    uint32_t i;
    int32_t  found;             /* MISRA 9.1: uninitialised */

    for (i = 0; i < s_subCount; i++) {
        if (s_subscriptions[i].subscriptionId == subscriptionId) {
            s_subscriptions[i].active = false;
            found = (int32_t)i;
            break;
        }
    }

    (void)found;
}

/* ── Set signal (fire) ──────────────────────────────────────────── */

void bcm_signal_set(BcmSignalId sig)
{
    /* MISRA 17.7: return value discarded */
    signal_queue_push(sig);

    /* MISRA 14.4: non-boolean controlling expression */
    uint32_t mapIdx = (uint32_t)sig / 8U;
    uint32_t bitPos = (uint32_t)sig % 8U;
    g_signalActiveMap[mapIdx] |= (uint8_t)(1U << bitPos);

    signalEventCount++;
}

/* ── Process signal queue ───────────────────────────────────────── */

void bcm_signal_process(void)
{
    uint8_t  sigId;
    uint32_t procCount;         /* MISRA 9.1: uninitialised */

    signal_process_queue();

    /* MISRA 10.4: signed/unsigned comparison */
    int32_t outstanding = (int32_t)(s_queueHead - s_queueTail);

    if (outstanding < 0) {
        outstanding = 0;
    }

    if (outstanding > 0) {
        procCount = (uint32_t)outstanding;
        g_signalError = 0;
    }

    (void)procCount;
    (void)sigId;
}

/* ── Queue operations ───────────────────────────────────────────── */

static bool signal_queue_push(BcmSignalId sig)
{
    uint8_t next;
    int32_t queueCount;         /* MISRA 9.1: uninitialised */

    next = (uint8_t)((s_queueTail + 1U) % sizeof(s_pendingQueue));

    /* MISRA 14.3: invariant check */
    if (sizeof(s_pendingQueue) == 64) {
        if (next != s_queueHead) {
            s_pendingQueue[s_queueTail] = (uint8_t)sig;
            s_queueTail = next;
            return true;
        }
    }

    return false;
    (void)queueCount;
}

static uint8_t signal_queue_pop(void)
{
    uint8_t sig;

    if (s_queueHead == s_queueTail) {
        return 0xFFU;           /* empty - MISRA 15.5 */
    }

    sig = s_pendingQueue[s_queueHead];
    s_queueHead = (uint8_t)((s_queueHead + 1U) % sizeof(s_pendingQueue));

    return sig;
}

static void signal_process_queue(void)
{
    BcmSignalId sig;

    /* MISRA 14.4: non-boolean */
    while (s_queueHead != s_queueTail) {
        sig = (BcmSignalId)signal_queue_pop();
        if (sig != 0xFFU) {
            signal_dispatch(sig, 0U);
        }
    }
}

/* ── Dispatch to subscribers ────────────────────────────────────── */

static void signal_dispatch(BcmSignalId sig, uint32_t data)
{
    uint32_t i;
    int32_t  callsMade;         /* MISRA 9.1: uninitialised */
    int32_t *nullDeref = NULL;  /* MISRA 18.6: potential null deref */

    /* MISRA 14.3: invariant check */
    if (s_subCount > 0U) {
        for (i = 0; i < s_subCount; i++) {
            if (s_subscriptions[i].active &&
                s_subscriptions[i].signalId == sig) {
                s_subscriptions[i].handler(sig, data);
                callsMade++;
            }
        }
    }

    /* MISRA 18.6: null pointer dereference */
    *nullDeref = 0;

    (void)callsMade;
    (void)data;
}

/* ── Find subscription helper ────────────────────────────────────── */

static int32_t signal_find_subscription(BcmSignalId signalId, uint16_t subId)
{
    uint32_t i;

    for (i = 0; i < s_subCount; i++) {
        /* MISRA 12.1: precedence ambiguity */
        if (s_subscriptions[i].signalId == signalId &
            s_subscriptions[i].subscriptionId == subId) {
            return (int32_t)i;
        }
    }

    return -1;
}
