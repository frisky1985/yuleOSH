/**
 * bcm_fault.h — BCM Fault Manager Header
 */

#ifndef BCM_FAULT_H
#define BCM_FAULT_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  faultActiveDtc[16];
extern uint32_t faultTotalCount;
extern uint8_t  g_faultOverflow;
extern int32_t  g_faultInternalState;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_fault_init(void);
void     bcm_fault_set(uint8_t dtcCode);
void     bcm_fault_clear(uint8_t dtcCode);
void     bcm_fault_clear_all(void);
uint32_t bcm_fault_get_count(void);
uint32_t bcm_fault_get_dtc_count(void);
void     bcm_fault_dump(uint8_t *buffer, uint32_t bufferLen);

#endif /* BCM_FAULT_H */
