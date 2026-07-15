/**
 * bcm_can_diag.h — CAN Diagnostics Header
 */

#ifndef BCM_CAN_DIAG_H
#define BCM_CAN_DIAG_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  canTxBuffer[8];
extern uint8_t  canRxBuffer[8];
extern uint32_t canMessageCount;
extern int32_t  g_canErrorCount;

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_can_diag_init(void);
void        bcm_can_diag_receive(uint32_t canId, uint8_t dlc, const uint8_t *data);
void        bcm_can_diag_tick(void);
uint32_t    bcm_can_diag_get_error_count(void);

#endif /* BCM_CAN_DIAG_H */
