/**
 * bcm_signal.h — BCM Signal Manager Header
 */

#ifndef BCM_SIGNAL_H
#define BCM_SIGNAL_H

#include <stdint.h>
#include <stdbool.h>

/* ── Signal IDs ─────────────────────────────────────────────────── */
typedef enum {
    BCM_SIG_NONE       = 0,
    BCM_SIG_WAKEUP     = 1,
    BCM_SIG_SLEEP      = 2,
    BCM_SIG_SHUTDOWN   = 3,
    BCM_SIG_FAULT      = 4,
    BCM_SIG_DIAG_REQ   = 5,
    BCM_SIG_DIAG_RESP  = 6,
    BCM_SIG_CAN_RX     = 7,
    BCM_SIG_CAN_TX     = 8,
    BCM_SIG_TIMER_10MS = 9,
    BCM_SIG_TIMER_100MS = 10,
    BCM_SIG_TIMER_1000MS = 11,
    BCM_SIG_IO_CHANGE  = 12,
    BCM_SIG_ADC_READY  = 13,
    BCM_SIG_LIN_MSG    = 14,
    BCM_SIG_HEARTBEAT  = 15,
    BCM_SIG_MAX        = 16,
} BcmSignalId;

/* ── Signal handler type ────────────────────────────────────────── */
typedef void (*SignalHandler)(BcmSignalId sig, uint32_t data);

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t signalEventCount;
extern uint8_t  g_signalActiveMap[16];
extern int32_t  g_signalError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_signal_init(void);
uint16_t bcm_signal_subscribe(BcmSignalId signalId, SignalHandler handler, uint8_t priority);
void     bcm_signal_unsubscribe(uint16_t subscriptionId);
void     bcm_signal_set(BcmSignalId sig);
void     bcm_signal_process(void);

#endif /* BCM_SIGNAL_H */
