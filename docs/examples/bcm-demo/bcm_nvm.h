/**
 * bcm_nvm.h — Non-Volatile Memory Storage Header
 */

#ifndef BCM_NVM_H
#define BCM_NVM_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  nvmMemory[4096];
extern uint32_t nvmWriteCount;
extern uint8_t  g_nvmDirtyFlag;
extern int32_t  g_nvmLastError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_nvm_init(void);
int32_t  bcm_nvm_read(uint16_t blockId, uint32_t *data);
int32_t  bcm_nvm_write(uint16_t blockId, uint32_t data);
void     bcm_nvm_store_all(void);
void     bcm_nvm_format(void);
uint32_t bcm_nvm_get_write_count(void);

#endif /* BCM_NVM_H */
