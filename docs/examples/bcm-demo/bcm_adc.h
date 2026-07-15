/**
 * bcm_adc.h — BCM ADC Driver Header
 */

#ifndef BCM_ADC_H
#define BCM_ADC_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint16_t adcRawValues[8];
extern uint32_t adcConversionCount;
extern uint8_t  g_adcChannelActive;
extern int32_t  g_adcLastError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_adc_init(void);
int32_t  bcm_adc_configure_sequence(const uint8_t *channels, uint32_t channelCount);
void     bcm_adc_trigger(void);
uint16_t bcm_adc_read_channel(uint8_t channel);
void     bcm_adc_read_all(void);
void     bcm_adc_start(void);
void     bcm_adc_stop(void);

#endif /* BCM_ADC_H */
