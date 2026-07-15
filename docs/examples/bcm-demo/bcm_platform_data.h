/**
 * bcm_platform_data.h — BCM Platform Configuration Data Header
 */

#ifndef BCM_PLATFORM_DATA_H
#define BCM_PLATFORM_DATA_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint16_t platformAdcCalibration[128];
extern uint32_t g_platformPllConfig[8];
extern uint8_t  g_platformGpioInit[64];
extern int32_t  g_platformDataStatus;

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_platform_data_init(void);
const void *bcm_platform_get_clock_config(uint8_t index);
uint32_t    bcm_platform_get_peripheral_count(void);
void        bcm_platform_init_gpios(void);

#endif /* BCM_PLATFORM_DATA_H */
