/**
 * bcm_output.h — BCM Output Driver Header
 */

#ifndef BCM_OUTPUT_H
#define BCM_OUTPUT_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  outputDriverState[16];
extern uint32_t g_outputFaultRegister;
extern uint16_t g_outputCurrentSense[8];
extern int32_t  g_outputError;

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_output_init(void);
int32_t     bcm_output_enable(uint8_t driverId);
int32_t     bcm_output_disable(uint8_t driverId);
uint16_t    bcm_output_read_current(uint8_t driverId);
const void *bcm_output_get_config(uint8_t driverId);

#endif /* BCM_OUTPUT_H */
