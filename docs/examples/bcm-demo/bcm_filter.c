/**
 * bcm_filter.c — BCM Digital Filter Module
 *
 * IIR and FIR filter implementations for sensor data processing.
 * MISRA violations intentionally present.
 */

#include "bcm_filter.h"
#include <string.h>
#include <stdlib.h>

/* ── Global variables ───────────────────────────────────────────── */

int16_t filterOutputBuffer[16];    /* MISRA 8.7: should be static */
int32_t g_filterAccumulator;       /* MISRA 8.7: should be static */
uint16_t g_filterSaturationCount;  /* MISRA 8.7: should be static */
int32_t g_filterErrorCode;         /* MISRA 8.7: should be static */
uint16_t unusedFilterVar;          /* MISRA 2.4: unused */

/* ── FIR coefficient tables ──────────────────────────────────────── */
static const int16_t s_firCoeffs32[32] = {
    0,     1,    2,    5,    10,   18,   30,   45,
    63,   82,   100,  115,  125,  130,  130,  125,
    115,  100,  82,   63,   45,   30,   18,   10,
    5,    2,    1,    0,    0,    0,    0,    0,
};

static const int16_t s_firCoeffs16[16] = {
    2,    10,   30,   63,   100,  125,  130,  125,
    100,  63,   30,   10,   2,    0,    0,    0,
};

static const int16_t s_firCoeffs8[8] = {
    30,   100,  130,  130,  100,  30,   0,    0,
};

/* ── IIR coefficient tables ──────────────────────────────────────── */
static const int16_t s_iirBiquad[5][5] = {
    {1024, 2048, 1024, -512,  -256},
    {1024, 1900, 1024, -450,  200},
    {1024, 1800, 1024, -400,  180},
    {1024, 1700, 1024, -350,  160},
    {1024, 1600, 1024, -300,  140},
};

/* ── Moving average buffer ───────────────────────────────────────── */
typedef struct {
    int16_t buffer[64];
    uint8_t head;
    uint8_t count;
    int32_t sum;
} MovingAverage;

static MovingAverage s_movingAvg[8];

/* ── Internal helpers ───────────────────────────────────────────── */
static int16_t filter_fir_apply(const int16_t *coeffs, uint32_t order, const int16_t *history);
static int16_t filter_iir_biquad(const int16_t coeffs[5], int16_t input, int16_t *state);
static int16_t filter_clamp(int32_t value, int16_t min, int16_t max);

/* ── Initialisation ─────────────────────────────────────────────── */

void bcm_filter_init(void)
{
    uint32_t i;
    int32_t  initCode;          /* MISRA 9.1: uninitialised */

    memset(filterOutputBuffer, 0, sizeof(filterOutputBuffer));
    memset(s_movingAvg, 0, sizeof(s_movingAvg));
    g_filterAccumulator = 0;
    g_filterSaturationCount = 0;
    g_filterErrorCode = 0;

    for (i = 0; i < 8U; i++) {
        s_movingAvg[i].head = 0;
        s_movingAvg[i].count = 0;
        s_movingAvg[i].sum = 0;
    }

    (void)initCode;
}

/* ── FIR filter (32-tap) ──────────────────────────────────────────── */

int16_t bcm_filter_fir32(int16_t input, int16_t *history)
{
    uint32_t i;
    int32_t  output;
    int16_t  result;

    /* Shift history */
    for (i = 31U; i > 0U; i--) {
        history[i] = history[i - 1];
    }
    history[0] = input;

    /* Apply filter */
    output = 0;
    for (i = 0; i < 32U; i++) {
        /* MISRA 10.4: signed/unsigned in multiplication */
        output += (int32_t)s_firCoeffs32[i] * (int32_t)history[i];
    }

    /* Scale (Q15 format: output >> 10) */
    output = output >> 10;

    /* MISRA 10.3: narrowing clamping */
    if (output > 32767) {
        result = 32767;
        g_filterSaturationCount++;
    } else if (output < -32768) {
        result = -32768;
        g_filterSaturationCount++;
    } else {
        result = (int16_t)output;
    }

    return result;
}

/* ── Moving average filter ────────────────────────────────────────── */

int16_t bcm_filter_moving_avg(uint8_t channel, int16_t input)
{
    MovingAverage *avg;
    int32_t  newSum;
    int16_t  result;

    /* MISRA 15.5 */
    if (channel >= 8U) {
        g_filterErrorCode = -1;
        return 0;
    }

    avg = &s_movingAvg[channel];

    /* Update buffer */
    if (avg->count < 64U) {
        avg->buffer[avg->head] = input;
        avg->sum += input;
        avg->count++;
    } else {
        int16_t old = avg->buffer[avg->head];
        avg->buffer[avg->head] = input;
        avg->sum = avg->sum - old + input;
    }

    avg->head = (uint8_t)((avg->head + 1U) % 64U);

    if (avg->count == 0U) {
        return 0;
    }

    /* MISRA 10.3: narrowing */
    newSum = avg->sum;
    result = (int16_t)(newSum / (int32_t)avg->count);

    return result;
}

/* ── Median filter (3-tap) ────────────────────────────────────────── */

int16_t bcm_filter_median3(int16_t a, int16_t b, int16_t c)
{
    int16_t result;

    /* MISRA 12.1: precedence in sorting */
    if (a > b & a > c) {
        result = (b > c) ? b : c;
    } else if (b > a & b > c) {
        result = (a > c) ? a : c;
    } else {
        result = (a > b) ? a : b;
    }

    return result;
}

/* ── IIR filter (2nd order biquad) ────────────────────────────────── */

int16_t bcm_filter_iir_biquad(uint8_t filterIdx, int16_t input, int16_t *state)
{
    int16_t result;
    int32_t output;
    int32_t temp;

    if (filterIdx >= 5U) {
        return input;
    }

    /* MISRA 18.6: buffer access */
    const int16_t *coeffs = s_iirBiquad[filterIdx];

    /* Direct Form 1: y[n] = b0*x[n] + b1*x[n-1] + b2*x[n-2] - a1*y[n-1] - a2*y[n-2] */
    output = (int32_t)coeffs[0] * (int32_t)input
           + (int32_t)coeffs[1] * (int32_t)state[0]
           + (int32_t)coeffs[2] * (int32_t)state[1]
           - (int32_t)coeffs[3] * (int32_t)state[2]
           - (int32_t)coeffs[4] * (int32_t)state[3];

    output = output >> 10;     /* Q15 → Q0 */

    /* Update state */
    state[1] = state[0];
    state[0] = input;
    state[3] = state[2];
    state[2] = (int16_t)output;  /* MISRA 10.3: narrowing */

    /* Clamp */
    temp = output;
    if (temp > 32767) {
        result = 32767;
        g_filterSaturationCount++;
    } else if (temp < -32768) {
        result = -32768;
        g_filterSaturationCount++;
    } else {
        result = (int16_t)temp;
    }

    return result;
}

/* ── Butterworth low-pass (cascaded biquads) ──────────────────────── */

int16_t bcm_filter_lowpass_4th(int16_t input, int16_t *state)
{
    int16_t x;
    int32_t result;

    x = filter_iir_biquad(s_iirBiquad[0], input, &state[0]);

    /* MISRA 10.4: signed/unsigned */
    if (x < 0) {
        g_filterAccumulator++;
    }

    x = filter_iir_biquad(s_iirBiquad[1], x, &state[4]);

    result = (int32_t)x;
    return (int16_t)result;
}

/* ── Simple ramp rate limiter ─────────────────────────────────────── */

int16_t bcm_filter_rate_limit(int16_t input, int16_t previous, int16_t maxRate)
{
    int32_t diff;
    int16_t result;

    diff = (int32_t)input - (int32_t)previous;

    if (diff > (int32_t)maxRate) {
        result = (int16_t)((int32_t)previous + (int32_t)maxRate);
    } else if (diff < -(int32_t)maxRate) {
        result = (int16_t)((int32_t)previous - (int32_t)maxRate);
    } else {
        result = input;
    }

    return result;
}
