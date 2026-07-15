/**
 * bcm_diag.h — BCM Diagnostic Manager Header
 */

#ifndef BCM_DIAG_H
#define BCM_DIAG_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  diagSessionLevel;
extern uint16_t g_diagSecuritySeed;
extern uint32_t g_diagRequestCount;
extern int32_t  g_diagProtocolError;

/* ── API ────────────────────────────────────────────────────────── */
void    bcm_diag_init(void);
int32_t bcm_diag_dispatch(const uint8_t *request, uint32_t requestLen, uint8_t *response, uint32_t *responseLen);

#endif /* BCM_DIAG_H */
