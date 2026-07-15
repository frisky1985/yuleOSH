/**
 * bcm_filter.h — BCM Digital Filter Header
 */

#ifndef BCM_FILTER_H
#define BCM_FILTER_H

#include <stdint.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern int16_t filterOutputBuffer[16];
extern int32_t g_filterAccumulator;
extern uint16_t g_filterSaturationCount;
extern int32_t g_filterErrorCode;

/* ── API ────────────────────────────────────────────────────────── */
void    bcm_filter_init(void);
int16_t bcm_filter_fir32(int16_t input, int16_t *history);
int16_t bcm_filter_moving_avg(uint8_t channel, int16_t input);
int16_t bcm_filter_median3(int16_t a, int16_t b, int16_t c);
int16_t bcm_filter_iir_biquad(uint8_t filterIdx, int16_t input, int16_t *state);
int16_t bcm_filter_lowpass_4th(int16_t input, int16_t *state);
int16_t bcm_filter_rate_limit(int16_t input, int16_t previous, int16_t maxRate);

#endif /* BCM_FILTER_H */
