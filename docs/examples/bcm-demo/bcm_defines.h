/**
 * bcm_defines.h — BCM Defines Header
 */

#ifndef BCM_DEFINES_H
#define BCM_DEFINES_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint16_t definesDtcCount;
extern uint16_t g_definesVersion;
extern uint8_t  g_definesConfigMode;
extern int32_t  g_definesError;

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_defines_init(void);
const void *bcm_defines_get_dtc(uint8_t dtcHigh, uint8_t dtcLow);
const void *bcm_defines_get_did(uint16_t did);

#endif /* BCM_DEFINES_H */
