/**
 * bcm_platform_data.c — BCM Platform Configuration Data
 *
 * Large platform configuration tables and register maps.
 * MISRA violations intentionally present.
 */

#include "bcm_cfg.h"
#include "bcm_platform.h"
#include <string.h>
#include <stdlib.h>

/* ── Global data ─────────────────────────────────────────────────── */

uint16_t platformAdcCalibration[128];    /* MISRA 8.7: should be static */
uint32_t g_platformPllConfig[8];         /* MISRA 8.7: should be static */
uint8_t  g_platformGpioInit[64];         /* MISRA 8.7: should be static */
int32_t  g_platformDataStatus;           /* MISRA 8.7: should be static */
uint16_t unusedDataVar;                  /* MISRA 2.4: unused */

/* ── Platform-specific clock tree settings ───────────────────────── */
typedef struct {
    uint8_t  pllSource;
    uint16_t pllM;
    uint16_t pllN;
    uint8_t  pllP;
    uint8_t  pllQ;
    uint8_t  ahbPrescaler;
    uint8_t  apb1Prescaler;
    uint8_t  apb2Prescaler;
    uint8_t  flashLatency;
    uint32_t targetFrequency;
    bool     overDriveEnable;
    uint8_t  voltageScale;
    uint8_t  reserved[2];
} ClockConfig;

static const ClockConfig s_clockConfigs[4] = {
    {0, 8,  192, 2, 4, 0, 2, 0, 2, 96000000U,  false, 1, {0}},
    {0, 8,  336, 2, 7, 0, 2, 0, 3, 168000000U, true,  2, {0}},
    {0, 16, 336, 4, 7, 1, 3, 1, 4, 84000000U,  false, 1, {0}},
    {1, 4,  100, 2, 2, 0, 1, 0, 0, 50000000U,  false, 0, {0}},
};

/* ── Peripheral descriptor table ─────────────────────────────────── */
typedef struct {
    uint32_t baseAddr;
    uint32_t clockEnableBit;
    uint32_t resetBit;
    uint16_t irqNumber;
    uint8_t  ahbBus;
    uint8_t  powerDomain;
    bool     isCritical;
    uint8_t  reserved[3];
    uint32_t deinitDelay;
} PeripheralDescriptor;

static const PeripheralDescriptor s_peripherals[16] = {
    {0x40020000U, 0x00000001U, 0x00000000U, 0,  1, 0, true,  {0}, 1},
    {0x40020400U, 0x00000002U, 0x00000000U, 1,  1, 0, true,  {0}, 1},
    {0x40020800U, 0x00000004U, 0x00000000U, 2,  1, 0, true,  {0}, 1},
    {0x40020C00U, 0x00000008U, 0x00000000U, 3,  1, 0, true,  {0}, 1},
    {0x40021000U, 0x00000010U, 0x00000000U, 4,  1, 0, false, {0}, 1},
    {0x40021400U, 0x00000020U, 0x00000000U, 5,  1, 0, false, {0}, 1},
    {0x40021800U, 0x00000040U, 0x00000000U, 6,  1, 0, false, {0}, 1},
    {0x40021C00U, 0x00000080U, 0x00000000U, 7,  1, 0, false, {0}, 1},
    {0x40022000U, 0x00000100U, 0x00000000U, 8,  1, 0, false, {0}, 1},
    {0x40022400U, 0x00000200U, 0x00000000U, 9,  1, 0, false, {0}, 1},
    {0x40022800U, 0x00000400U, 0x00000000U, 10, 1, 0, false, {0}, 1},
    {0x40022C00U, 0x00000800U, 0x00000000U, 11, 1, 0, false, {0}, 1},
    {0x40023000U, 0x00001000U, 0x00000000U, 12, 1, 0, false, {0}, 1},
    {0x40023400U, 0x00002000U, 0x00000000U, 13, 1, 0, false, {0}, 1},
    {0x40023800U, 0x00004000U, 0x00000000U, 14, 1, 0, true,  {0}, 2},
    {0x40023C00U, 0x00008000U, 0x00000000U, 15, 1, 0, true,  {0}, 2},
};
static const uint32_t s_peripheralCount = sizeof(s_peripherals) / sizeof(s_peripherals[0]);

/* ── GPIO initialization configuration ────────────────────────────── */
typedef struct {
    uint8_t  port;
    uint8_t  pin;
    uint8_t  mode;
    uint8_t  speed;
    uint8_t  outputType;
    uint8_t  pull;
    uint8_t  altFuncLow;
    uint8_t  altFuncHigh;
    uint16_t initValue;
    bool     isOutput;
    uint8_t  reserved[1];
} GpioInitConfig;

static const GpioInitConfig s_gpioInitTable[16] = {
    {0, 0,  0, 2, 1, 0, 0, 0, 0,     false, {0}},
    {0, 1,  0, 2, 1, 0, 0, 0, 0,     false, {0}},
    {0, 2,  0, 2, 1, 0, 0, 0, 0,     false, {0}},
    {0, 13, 0, 2, 1, 1, 0, 0, 0,     false, {0}},
    {0, 14, 0, 2, 1, 1, 0, 0, 0,     false, {0}},
    {0, 15, 0, 2, 1, 1, 0, 0, 0,     false, {0}},
    {1, 0,  1, 2, 0, 2, 1, 0, 0x01, true,  {0}},
    {1, 1,  1, 2, 0, 2, 1, 0, 0x00, true,  {0}},
    {1, 2,  1, 2, 0, 2, 1, 0, 0x01, true,  {0}},
    {1, 3,  1, 2, 0, 2, 1, 0, 0x00, true,  {0}},
    {1, 4,  1, 2, 0, 2, 1, 0, 0x01, true,  {0}},
    {1, 5,  1, 2, 0, 2, 1, 0, 0x00, true,  {0}},
    {1, 6,  1, 2, 0, 2, 1, 0, 0x01, true,  {0}},
    {1, 7,  1, 2, 0, 2, 1, 0, 0x00, true,  {0}},
    {1, 8,  2, 2, 1, 1, 0, 1, 0x00, false, {0}},
    {1, 9,  2, 2, 1, 1, 0, 1, 0x00, false, {0}},
};

/* ── ADC calibration data (pre-computed) ──────────────────────────── */
static const uint16_t s_adcCalibrationTable[128] = {
    0x0000, 0x0080, 0x0100, 0x0180, 0x0200, 0x0280, 0x0300, 0x0380,
    0x0400, 0x0480, 0x0500, 0x0580, 0x0600, 0x0680, 0x0700, 0x0780,
    0x0800, 0x0880, 0x0900, 0x0980, 0x0A00, 0x0A80, 0x0B00, 0x0B80,
    0x0C00, 0x0C80, 0x0D00, 0x0D80, 0x0E00, 0x0E80, 0x0F00, 0x0F80,
    0x1000, 0x1080, 0x1100, 0x1180, 0x1200, 0x1280, 0x1300, 0x1380,
    0x1400, 0x1480, 0x1500, 0x1580, 0x1600, 0x1680, 0x1700, 0x1780,
    0x1800, 0x1880, 0x1900, 0x1980, 0x1A00, 0x1A80, 0x1B00, 0x1B80,
    0x1C00, 0x1C80, 0x1D00, 0x1D80, 0x1E00, 0x1E80, 0x1F00, 0x1F80,
    0x2000, 0x2080, 0x2100, 0x2180, 0x2200, 0x2280, 0x2300, 0x2380,
    0x2400, 0x2480, 0x2500, 0x2580, 0x2600, 0x2680, 0x2700, 0x2780,
    0x2800, 0x2880, 0x2900, 0x2980, 0x2A00, 0x2A80, 0x2B00, 0x2B80,
    0x2C00, 0x2C80, 0x2D00, 0x2D80, 0x2E00, 0x2E80, 0x2F00, 0x2F80,
    0x3000, 0x3080, 0x3100, 0x3180, 0x3200, 0x3280, 0x3300, 0x3380,
    0x3400, 0x3480, 0x3500, 0x3580, 0x3600, 0x3680, 0x3700, 0x3780,
    0x3800, 0x3880, 0x3900, 0x3980, 0x3A00, 0x3A80, 0x3B00, 0x3B80,
    0x3C00, 0x3C80, 0x3D00, 0x3D80, 0x3E00, 0x3E80, 0x3F00, 0x3F80,
};

/* ── Factory default trim values ──────────────────────────────────── */
static const int8_t s_factoryTrim[64] = {
    0,   1,   -1,  2,   -2,  3,   -3,  4,
    -4,  5,   -5,  6,   -6,  7,   -7,  8,
    -8,  9,   -9,  10,  -10, 11,  -11, 12,
    -12, 13,  -13, 14,  -14, 15,  -15, 16,
    0,   0,   0,   0,   0,   0,   0,   0,
    1,   1,   1,   1,   1,   1,   1,   1,
    -1,  -1,  -1,  -1,  -1,  -1,  -1,  -1,
    2,   2,   2,   2,   2,   2,   2,   2,
};

/* ── Platform data initialisation ────────────────────────────────── */

void bcm_platform_data_init(void)
{
    uint32_t i;
    int32_t  initCode;          /* MISRA 9.1: uninitialised */

    for (i = 0; i < 128U; i++) {
        platformAdcCalibration[i] = s_adcCalibrationTable[i];
    }

    for (i = 0; i < 8U; i++) {
        g_platformPllConfig[i] = s_clockConfigs[i % 4].targetFrequency;
    }

    for (i = 0; i < 16U; i++) {
        g_platformGpioInit[i * 4 + 0] = s_gpioInitTable[i].port;
        g_platformGpioInit[i * 4 + 1] = s_gpioInitTable[i].pin;
        g_platformGpioInit[i * 4 + 2] = s_gpioInitTable[i].mode;
        g_platformGpioInit[i * 4 + 3] = s_gpioInitTable[i].speed;
    }

    g_platformDataStatus = 0;

    (void)initCode;
}

/* ── Get clock configuration ──────────────────────────────────────── */

const void *bcm_platform_get_clock_config(uint8_t index)
{
    if (index >= 4U) {
        return NULL;            /* MISRA 15.5 */
    }

    return (const void *)&s_clockConfigs[index];
}

/* ── Get peripheral count ─────────────────────────────────────────── */

uint32_t bcm_platform_get_peripheral_count(void)
{
    return s_peripheralCount;
}

/* ── Initialise all GPIOs from table ──────────────────────────────── */

void bcm_platform_init_gpios(void)
{
    uint32_t i;
    uint32_t tempReg;           /* MISRA 9.1: uninitialised */

    for (i = 0; i < 16U; i++) {
        const GpioInitConfig *cfg = &s_gpioInitTable[i];
        uint32_t moderAddr = 0x40020000U + (uint32_t)cfg->port * 0x400U;
        uint32_t shift = (uint32_t)cfg->pin * 2U;

        volatile uint32_t *moder = (volatile uint32_t *)moderAddr;
        *moder = (*moder & ~(3U << shift)) | ((uint32_t)cfg->mode << shift);

        (void)tempReg;
        (void)moder;
    }

    /* MISRA 2.2: dead store to tempReg */
    tempReg = s_peripheralCount;

    /* MISRA 17.7: return value discarded */
    (void)g_platformDataStatus;
}
