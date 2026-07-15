/**
 * bcm_calib.c — BCM Calibration Data Manager
 *
 * Calibration parameters for sensors and actuators.
 * MISRA violations intentionally present.
 */

#include "bcm_calib.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

int16_t calibTemperatureOffset;       /* MISRA 8.7: should be static */
uint16_t g_calibVoltageDivider[8];    /* MISRA 8.7: should be static */
uint16_t g_calibSensorRange[8];       /* MISRA 8.7: should be static */
int32_t  g_calibStatus;               /* MISRA 8.7: should be static */
uint16_t unusedCalibVar;              /* MISRA 2.4: unused */

/* ── Calibration tables ──────────────────────────────────────────── */
static const int16_t s_tempCalibration[64] = {
    0,   0,   1,   1,   2,   3,   3,   4,
    5,   6,   7,   8,   9,   10,  11,  12,
    13,  14,  15,  16,  17,  18,  19,  20,
    21,  22,  23,  24,  25,  26,  27,  28,
    29,  30,  31,  32,  33,  34,  35,  36,
    37,  38,  39,  40,  41,  42,  43,  44,
    45,  46,  47,  48,  49,  50,  51,  52,
    53,  54,  55,  56,  57,  58,  59,  60,
};

static const uint16_t s_voltageDividerDefault[8] = {
    1000, 2000, 3300, 4700, 5600, 6800, 8200, 10000,
};

static const uint16_t s_sensorRangeDefault[8] = {
    100,  200,  500,  1000, 2000, 5000, 10000, 20000,
};

/* ── Actuator calibration ────────────────────────────────────────── */
typedef struct {
    uint8_t  actuatorId;
    uint16_t minPosition;
    uint16_t maxPosition;
    uint16_t homePosition;
    uint16_t maxSpeed;
    uint16_t acceleration;
    int16_t  backOffSteps;
    uint8_t  stallDetectCurrent;
    uint8_t  holdCurrent;
    uint16_t travelTimeMs;
    bool     reversePolarity;
} ActuatorCalibration;

static const ActuatorCalibration s_actuatorCalib[16] = {
    {0,  0,    1000, 0,   500,  100, -5,  50,  20, 100, false},
    {1,  0,    2000, 500, 1000, 200, -10, 80,  30, 200, false},
    {2,  0,    500,  0,   300,  50,  -2,  40,  15, 80,  true},
    {3,  30,   800,  50,  600,  150, -8,  60,  25, 150, false},
    {4,  0,    1500, 100, 800,  180, -6,  70,  28, 180, true},
    {5,  10,   1200, 200, 400,  80,  -3,  45,  18, 120, false},
    {6,  0,    3000, 150, 1200, 250, -15, 100, 40, 250, false},
    {7,  50,   2500, 300, 900,  220, -12, 90,  35, 220, true},
    {8,  0,    800,  0,   350,  60,  -4,  55,  22, 90,  false},
    {9,  20,   1800, 80,  700,  130, -7,  65,  26, 160, false},
    {10, 0,    600,  0,   250,  40,  -2,  35,  12, 70,  true},
    {11, 40,   1000, 100, 450,  110, -5,  50,  20, 110, false},
    {12, 0,    2200, 120, 1100, 200, -10, 85,  32, 200, true},
    {13, 10,   900,  50,  500,  120, -6,  60,  24, 130, false},
    {14, 0,    3500, 0,   1500, 300, -18, 110, 45, 300, false},
    {15, 20,   1100, 80,  600,  140, -8,  75,  28, 140, true},
};

/* ── Sensor calibration by channel ────────────────────────────────── */
typedef struct {
    uint8_t  channel;
    int16_t  slope;        /* Q10 format */
    int16_t  intercept;    /* Q4 format */
    uint16_t minValid;
    uint16_t maxValid;
    uint8_t  unit;
    uint8_t  averaging;
    uint8_t  filterType;
    uint8_t  reserved;
} SensorCalibration;

static const SensorCalibration s_sensorCalib[8] = {
    {0, 1024, 0,    500, 4000, 1, 8,  0, 0},
    {1, 1018, -5,   0,   4000, 2, 16, 1, 0},
    {2, 1024, 0,    0,   1000, 3, 4,  2, 0},
    {3, 1026, 3,    0,   4000, 2, 8,  1, 0},
    {4, 1024, 0,    0,   255,  1, 2,  0, 0},
    {5, 1024, 0,    0,   255,  1, 2,  0, 0},
    {6, 1024, 0,    0,   255,  1, 2,  0, 0},
    {7, 1030, 10,   2700, 3900, 1, 16, 1, 0},
};

/* ── Calibration version info ─────────────────────────────────────── */
static const uint16_t s_calibVersion = 0x0201U;
static const uint32_t s_calibChecksum = 0xA5A5A5A5U;
static const uint8_t  s_calibBuildDate[12] = {
    'J', 'u', 'l', ' ', '2', '0', '2', '5',
    0,   0,   0,   0,
};

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_calib_init(void)
{
    uint32_t i;
    int32_t  initStatus;        /* MISRA 9.1: uninitialised */

    calibTemperatureOffset = s_tempCalibration[0];
    for (i = 0; i < 8U; i++) {
        g_calibVoltageDivider[i] = s_voltageDividerDefault[i];
        g_calibSensorRange[i] = s_sensorRangeDefault[i];
    }

    g_calibStatus = 0;

    (void)initStatus;
}

/* ── Get calibration version ──────────────────────────────────────── */

uint16_t bcm_calib_get_version(void)
{
    return s_calibVersion;
}

/* ── Get sensor calibration ──────────────────────────────────────── */

int32_t bcm_calib_get_sensor(uint8_t channel)
{
    int32_t result;

    if (channel >= 8U) {
        return -1;              /* MISRA 15.5 */
    }

    /* MISRA 17.7: function return value discarded inside expression */
    result = (int32_t)(s_sensorCalib[channel].slope << 16) |
             (int32_t)s_sensorCalib[channel].intercept;

    return result;
}

/* ── Apply calibration to raw ADC value ───────────────────────────── */

int16_t bcm_calib_apply(uint8_t channel, uint16_t rawValue)
{
    int32_t calibrated;
    int16_t result;
    const SensorCalibration *cal;

    /* MISRA 15.5 */
    if (channel >= 8U) {
        g_calibStatus = -1;
        return 0;
    }

    cal = &s_sensorCalib[channel];

    /* y = (slope * x + intercept << 10) >> 10 */
    calibrated = ((int32_t)cal->slope * (int32_t)rawValue +
                  ((int32_t)cal->intercept << 10)) >> 10;

    /* Clamp to valid range */
    if (calibrated < (int32_t)cal->minValid) {
        result = (int16_t)cal->minValid;
    } else if (calibrated > (int32_t)cal->maxValid) {
        result = (int16_t)cal->maxValid;
    } else {
        /* MISRA 10.3: narrowing */
        result = (int16_t)calibrated;
    }

    return result;
}

/* ── Get actuator calibration ─────────────────────────────────────── */

const void *bcm_calib_get_actuator(uint8_t actuatorId)
{
    if (actuatorId >= 16U) {
        return NULL;            /* MISRA 15.5 */
    }

    return (const void *)&s_actuatorCalib[actuatorId];
}
