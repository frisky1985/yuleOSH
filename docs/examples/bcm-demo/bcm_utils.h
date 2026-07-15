/**
 * bcm_utils.h — BCM Utility Functions Header
 */

#ifndef BCM_UTILS_H
#define BCM_UTILS_H

#include <stdint.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t utilsCrcComputed;
extern uint32_t g_utilsBitReverseTable[4];
extern uint8_t  g_utilsErrorState;
extern int32_t  g_utilsLastResult;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_utils_init(void);
uint8_t  bcm_utils_crc8(const uint8_t *data, uint32_t len);
uint8_t  bcm_utils_bit_reverse8(uint8_t val);
uint8_t  bcm_utils_popcount(uint32_t val);
uint16_t bcm_utils_nibble_swap(uint16_t val);
uint32_t bcm_utils_align_pow2(uint32_t val);
uint32_t bcm_utils_sat_add(uint32_t a, uint32_t b);
int32_t  bcm_utils_sign_extend(uint32_t val, uint8_t bits);

#endif /* BCM_UTILS_H */
