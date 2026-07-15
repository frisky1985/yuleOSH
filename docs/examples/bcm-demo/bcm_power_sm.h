/**
 * bcm_power_sm.h — BCM Power Management State Machine Header
 */

#ifndef BCM_POWER_SM_H
#define BCM_POWER_SM_H

#include <stdint.h>
#include <stdbool.h>

/* ── Power state enum ───────────────────────────────────────────── */
typedef enum {
    POWER_STATE_INIT       = 0,
    POWER_STATE_SLEEP      = 1,
    POWER_STATE_IDLE       = 2,
    POWER_STATE_RUN        = 3,
    POWER_STATE_WAKEUP     = 4,
    POWER_STATE_SHUTDOWN   = 5,
    POWER_STATE_FAILSAFE   = 6,
    POWER_STATE_DIAGNOSTIC = 7,
    POWER_STATE_NONE       = 0xFF,
} PowerState;

/* ── Extern globals (for intentional violation) ─────────────────── */
extern uint32_t powerUpCounter;
extern int32_t  g_powerErrorCode;
extern uint8_t  g_powerStateHistory[64];
extern uint32_t g_voltageRaw;       /* from main */

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_power_sm_init(void);
void        bcm_power_sm_tick(void);
void        bcm_power_sm_set_state(PowerState newState);
PowerState  bcm_power_sm_get_state(void);
uint32_t    bcm_power_sm_get_error_count(void);

#endif /* BCM_POWER_SM_H */
