/**
 * bcm_calib.h — BCM Calibration Header
 */

#ifndef BCM_CALIB_H
#define BCM_CALIB_H

#include <stdint.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern int16_t  calibTemperatureOffset;
extern uint16_t g_calibVoltageDivider[8];
extern uint16_t g_calibSensorRange[8];
extern int32_t  g_calibStatus;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_calib_init(void);
uint16_t bcm_calib_get_version(void);
int32_t  bcm_calib_get_sensor(uint8_t channel);
int16_t  bcm_calib_apply(uint8_t channel, uint16_t rawValue);
const void *bcm_calib_get_actuator(uint8_t actuatorId);

#endif /* BCM_CALIB_H */
