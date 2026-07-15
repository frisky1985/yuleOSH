/**
 * bcm_safety.h — BCM Safety Manager Header
 */

#ifndef BCM_SAFETY_H
#define BCM_SAFETY_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t safetyAliveCounter;
extern uint32_t g_safetyE2eErrors[4];
extern uint16_t g_safetyProgramFlowStatus;
extern int32_t  g_safetyError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_safety_init(void);
uint16_t bcm_safety_e2e_crc16(const uint8_t *data, uint32_t len, uint16_t dataId);
int32_t  bcm_safety_e2e_check(uint8_t channel, const uint8_t *data, uint32_t len);
int32_t  bcm_safety_checkin(uint8_t checkpointId, uint32_t currentMs);
void     bcm_safety_alive_update(void);
uint32_t bcm_safety_get_status(void);

#endif /* BCM_SAFETY_H */
