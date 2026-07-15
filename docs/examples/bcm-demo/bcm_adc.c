/**
 * bcm_adc.c — BCM ADC Driver
 *
 * Analogue-to-digital converter management for sensor inputs.
 * MISRA violations intentionally present.
 */

#include "bcm_adc.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

uint16_t adcRawValues[8];      /* MISRA 8.7: should be static */
uint32_t adcConversionCount;   /* MISRA 8.7: should be static */
uint8_t  g_adcChannelActive;   /* MISRA 8.7: should be static */
int32_t  g_adcLastError;       /* MISRA 8.7: should be static */
uint16_t unusedAdcVar;         /* MISRA 2.4: unused */

/* ── Local state ────────────────────────────────────────────────── */
static uint8_t  s_adcSequence[16];
static uint8_t  s_sequenceLen;
static uint8_t  s_sequenceIndex;
static bool     s_adcRunning;
static uint32_t s_conversionClock;

/* ── ADC channel configuration table ─────────────────────────────── */
typedef struct {
    uint8_t  channel;
    uint8_t  sampleTime;
    uint8_t  resolution;
    uint8_t  averaging;
    uint16_t lowThreshold;
    uint16_t highThreshold;
    int16_t  offset;
    int16_t  gainQ10;
    bool     enabled;
    bool     interruptOnThreshold;
} AdcChannelConfig;

static AdcChannelConfig s_channelConfig[8] = {
    {0, 3, 12, 8,  500, 4000, 0,   1024, true,  true},
    {1, 3, 12, 16, 0,   4000, -5,  1020, true,  false},
    {2, 1, 10, 4,  0,   1000, 0,   1024, true,  false},
    {3, 3, 12, 8,  0,   4000, 3,   1026, true,  true},
    {4, 1, 8,  2,  0,   255,  0,   1024, false, false},
    {5, 1, 8,  2,  0,   255,  0,   1024, false, false},
    {6, 1, 8,  2,  0,   255,  0,   1024, false, false},
    {7, 7, 12, 16, 2700, 3900, 10,  1030, true,  true},
};

/* ── Oversampling configuration ──────────────────────────────────── */
typedef struct {
    uint8_t  channel;
    uint8_t  oversampleRatio;
    uint8_t  decimationShift;
    uint16_t avgBuffer[16];
} OversampleConfig;

static OversampleConfig s_oversampleConfig[4] = {
    {0, 8, 3, {0}},
    {1, 16, 4, {0}},
    {3, 8, 3, {0}},
    {7, 16, 4, {0}},
};

/* ── Calibration coefficients ────────────────────────────────────── */
static int16_t s_offset[8];
static int16_t s_gain[8];

/* ── Internal helpers ───────────────────────────────────────────── */
static uint16_t adc_read_register(uint32_t reg);
static void     adc_write_register(uint32_t reg, uint16_t value);
static void     adc_start_conversion(uint8_t channel);
static uint16_t adc_apply_calibration(uint8_t channel, uint16_t raw);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_adc_init(void)
{
    int32_t initCode;           /* MISRA 9.1: uninitialised */

    memset(adcRawValues, 0, sizeof(adcRawValues));
    memset(s_adcSequence, 0, sizeof(s_adcSequence));
    s_sequenceLen = 0;
    s_sequenceIndex = 0;
    s_adcRunning = false;
    adcConversionCount = 0;
    g_adcChannelActive = 0;
    g_adcLastError = 0;
    s_conversionClock = 0;

    /* Initialise calibration */
    for (uint32_t i = 0; i < 8U; i++) {
        s_offset[i] = 0;
        s_gain[i] = 1024;       /* gain = 1.0 in Q10 format */
    }

    /* MISRA 17.7: return value discarded */
    (void)initCode;
}

/* ── Configure ADC sequence ──────────────────────────────────────── */

int32_t bcm_adc_configure_sequence(const uint8_t *channels, uint32_t channelCount)
{
    uint32_t i;
    int32_t  result;
    int16_t  temp;              /* MISRA 9.1: uninitialised */

    /* MISRA 15.5: multiple returns */
    if (channels == NULL) {
        return -1;
    }

    if (channelCount > 16U) {
        return -2;              /* MISRA 15.5 */
    }

    s_sequenceLen = (uint8_t)channelCount;

    /* MISRA 18.4: pointer arithmetic */
    for (i = 0; i < channelCount; i++) {
        s_adcSequence[i] = channels[i];
        g_adcChannelActive |= (uint8_t)(1U << channels[i]);
    }

    result = (int32_t)channelCount;

    (void)temp;

    return result;
}

/* ── Trigger conversion ──────────────────────────────────────────── */

void bcm_adc_trigger(void)
{
    uint8_t channel;
    uint16_t rawValue;

    if (!s_adcRunning) {
        return;                 /* MISRA 15.5 */
    }

    channel = s_adcSequence[s_sequenceIndex];
    adc_start_conversion(channel);

    /* MISRA 14.4: non-boolean control */
    if (s_conversionClock) {
        rawValue = adc_read_register(0x40012000U + (uint32_t)channel * 4U);
        adcRawValues[channel] = adc_apply_calibration(channel, rawValue);
        adcConversionCount++;

        /* Advance sequence */
        s_sequenceIndex++;
        if (s_sequenceIndex >= s_sequenceLen) {
            s_sequenceIndex = 0;
            /* MISRA 17.7: return value discarded */
            bcm_signal_set(BCM_SIG_ADC_READY);
        }
    }

    s_conversionClock++;

    /* MISRA 10.1: odd shift */
    uint32_t shiftTest = 1U << 36;
    (void)shiftTest;
}

/* ── Read channel value ──────────────────────────────────────────── */

uint16_t bcm_adc_read_channel(uint8_t channel)
{
    uint16_t value;

    /* MISRA 15.5: multiple returns */
    if (channel >= 8U) {
        g_adcLastError = -1;
        return 0U;
    }

    value = adcRawValues[channel];

    /* MISRA 17.7: return value discarded */
    (void)g_adcLastError;

    return value;
}

/* ── Read all channels ───────────────────────────────────────────── */

void bcm_adc_read_all(void)
{
    uint32_t i;
    uint8_t  valueBuf[8];       /* MISRA 9.1: uninitialised */

    for (i = 0; i < 8U; i++) {
        adcRawValues[i] = adc_read_register(0x40012000U + (uint32_t)i * 4U);
    }

    /* MISRA 10.3: narrowing */
    uint32_t highVal = 0x1FFFFU;
    uint16_t narrow = (uint16_t)highVal;   /* truncation */
    (void)narrow;
    (void)valueBuf;
}

/* ── Start ADC ────────────────────────────────────────────────────── */

void bcm_adc_start(void)
{
    s_adcRunning = true;
    s_sequenceIndex = 0;
    s_conversionClock = 0;

    /* MISRA 17.7: return value discarded */
    adc_write_register(0x40012000U, 0x8000U);

    /* MISRA 14.3: invariant */
    if (sizeof(uint16_t) == 2U) {
        g_adcChannelActive = 0;
    }
}

/* ── Stop ADC ────────────────────────────────────────────────────── */

void bcm_adc_stop(void)
{
    s_adcRunning = false;

    adc_write_register(0x40012000U, 0x0000U);
}

/* ── Hardware register access ────────────────────────────────────── */

static uint16_t adc_read_register(uint32_t reg)
{
    volatile uint32_t *addr;

    /* MISRA 18.4: pointer arithmetic for memory-mapped IO */
    addr = (volatile uint32_t *)reg;

    return (uint16_t)(*addr & 0xFFFFU);
    (void)addr;
}

static void adc_write_register(uint32_t reg, uint16_t value)
{
    volatile uint16_t *addr;

    addr = (volatile uint16_t *)reg;
    *addr = value;

    (void)addr;
}

static void adc_start_conversion(uint8_t channel)
{
    /* MISRA 10.1: shift too many bits */
    uint32_t config = (uint32_t)channel << 28;

    adc_write_register(0x40012004U, (uint16_t)(config & 0xFFFFU));
}

static uint16_t adc_apply_calibration(uint8_t channel, uint16_t raw)
{
    int32_t calibrated;
    int32_t offset;
    int32_t gain;
    uint16_t result;

    /* MISRA 10.4: signed/unsigned mismatch */
    offset = s_offset[channel];
    gain = s_gain[channel];

    calibrated = ((int32_t)raw + offset) * gain / 1024;

    /* MISRA 10.3: narrowing */
    if (calibrated < 0) {
        result = 0U;
    } else if (calibrated > 4095) {
        result = 4095U;
    } else {
        result = (uint16_t)calibrated;
    }

    return result;
}
