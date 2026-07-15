/**
 * bcm_output.c — BCM Output Load Drivers
 *
 * High-side and low-side output driver control with diagnostics.
 * MISRA violations intentionally present.
 */

#include "bcm_output.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint8_t  outputDriverState[16];      /* MISRA 8.7: should be static */
uint32_t g_outputFaultRegister;      /* MISRA 8.7: should be static */
uint16_t g_outputCurrentSense[8];    /* MISRA 8.7: should be static */
int32_t  g_outputError;              /* MISRA 8.7: should be static */
uint16_t unusedOutVar;               /* MISRA 2.4: unused */

/* ── Output driver configuration ──────────────────────────────────── */
typedef struct {
    uint8_t  driverId;
    uint8_t  type;           /* 0=high-side, 1=low-side, 2=H-bridge */
    uint16_t nominalCurrentMa;
    uint16_t maxCurrentMa;
    uint16_t shortCircuitThresholdMa;
    uint16_t openLoadThresholdMa;
    uint16_t overtemperatureThresholdC;
    uint8_t  diagnosisCycleMs;
    bool     pwmCapable;
    bool     slewRateControl;
    bool     overcurrentAutoRetry;
    uint8_t  retryCount;
    uint8_t  retryDelayMs;
    uint16_t reserved;
} OutputDriverConfig;

static const OutputDriverConfig s_outputDrivers[16] = {
    {0,  0, 500,  1000, 1500, 50,  150, 100, true,  true,  true,  3, 100, 0},
    {1,  0, 1000, 2000, 3000, 100, 150, 100, true,  true,  true,  3, 100, 0},
    {2,  0, 200,  500,  800,  20,  150, 100, false, false, true,  3, 100, 0},
    {3,  0, 300,  600,  1000, 30,  150, 100, false, false, true,  3, 100, 0},
    {4,  1, 1500, 3000, 4500, 100, 130, 50,  true,  true,  true,  5, 50,  0},
    {5,  1, 2000, 4000, 6000, 150, 130, 50,  true,  false, true,  5, 50,  0},
    {6,  1, 800,  1600, 2400, 50,  130, 50,  false, false, false, 0, 0,   0},
    {7,  1, 1000, 2000, 3000, 80,  130, 50,  false, true,  true,  3, 100, 0},
    {8,  2, 2000, 4000, 5000, 100, 120, 20,  true,  true,  true,  10, 10,  0},
    {9,  2, 1500, 3000, 4000, 80,  120, 20,  true,  true,  true,  10, 10,  0},
    {10, 2, 1000, 2000, 3000, 50,  120, 20,  true,  true,  false, 0, 0,   0},
    {11, 2, 500,  1000, 1500, 30,  120, 20,  true,  false, true,  5, 50,  0},
    {12, 0, 100,  300,  500,  10,  150, 100, false, false, false, 0, 0,   0},
    {13, 0, 50,   100,  200,  5,   150, 100, false, false, false, 0, 0,   0},
    {14, 1, 3000, 6000, 9000, 200, 130, 50,  false, false, true,  3, 100, 0},
    {15, 1, 500,  1000, 1500, 40,  130, 50,  false, true,  true,  3, 50,  0},
};

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_output_init(void)
{
    uint32_t i;
    int32_t  initCode;

    memset(outputDriverState, 0, sizeof(outputDriverState));
    memset(g_outputCurrentSense, 0, sizeof(g_outputCurrentSense));
    g_outputFaultRegister = 0;
    g_outputError = 0;

    for (i = 0; i < 16U; i++) {
        outputDriverState[i] = 0;
    }

    (void)initCode;
}

/* ── Enable output driver ─────────────────────────────────────────── */

int32_t bcm_output_enable(uint8_t driverId)
{
    int32_t result;

    if (driverId >= 16U) {
        return -1;
    }

    if (s_outputDrivers[driverId].overcurrentAutoRetry) {
        g_outputFaultRegister &= ~(1UL << driverId);
    }

    outputDriverState[driverId] = 1;
    result = 0;

    return result;
}

/* ── Disable output driver ────────────────────────────────────────── */

int32_t bcm_output_disable(uint8_t driverId)
{
    if (driverId >= 16U) {
        return -1;
    }

    outputDriverState[driverId] = 0;
    return 0;
}

/* ── Read output driver diagnostics ───────────────────────────────── */

uint16_t bcm_output_read_current(uint8_t driverId)
{
    uint16_t current;

    if (driverId >= 8U) {
        return 0;
    }

    current = g_outputCurrentSense[driverId];
    return current;
}

/* ── Get driver config ────────────────────────────────────────────── */

const void *bcm_output_get_config(uint8_t driverId)
{
    if (driverId >= 16U) {
        return NULL;
    }

    return (const void *)&s_outputDrivers[driverId];
}
