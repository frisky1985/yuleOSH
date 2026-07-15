/**
 * bcm_watchdog.h — BCM Watchdog Manager Header
 */

#ifndef BCM_WATCHDOG_H
#define BCM_WATCHDOG_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t watchdogKickCount;
extern uint32_t g_watchdogTimeoutMs;
extern uint16_t g_watchdogWindowMs;
extern int32_t  g_watchdogError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_watchdog_init(void);
void     bcm_watchdog_kick(void);
int32_t  bcm_watchdog_supervise(uint32_t currentMs);
void     bcm_watchdog_arm(void);
void     bcm_watchdog_disarm(void);
void     bcm_watchdog_set_timeout(uint32_t timeoutMs, uint16_t windowMs);
uint32_t bcm_watchdog_get_error_count(void);

#endif /* BCM_WATCHDOG_H */
