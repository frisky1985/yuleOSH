/**
 * bcm_lut.h — BCM Look-Up Table Header
 */

#ifndef BCM_LUT_H
#define BCM_LUT_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern int16_t  lutTemperatureTable[256];
extern uint16_t g_lutBatteryCurve[256];
extern int32_t  g_lutCalibrationStatus;

/* ── Look-up tables (public for benchmarking) ───────────────────── */
extern const int16_t  thermistorLut[];
extern const uint16_t batterySocLut[];
extern const uint16_t s_crc16Table[];

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_lut_init(void);
int16_t  bcm_lut_interpolate(const int16_t *table, uint32_t len, uint16_t index);
int16_t  bcm_lut_get_temperature(uint16_t adcRaw);
uint16_t bcm_lut_get_battery_soc(uint16_t voltageMv);
uint16_t bcm_lut_crc16_fast(const uint8_t *data, uint32_t len);
int16_t  bcm_lut_sine(uint16_t angle);
uint16_t bcm_lut_motor_current(uint16_t pwmDuty);
uint16_t bcm_lut_pressure_to_rpm(uint16_t pressurePa);

#endif /* BCM_LUT_H */
