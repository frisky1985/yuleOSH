/**
 * bcm_boot.h — BCM Bootloader Support Header
 */

#ifndef BCM_BOOT_H
#define BCM_BOOT_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t bootAppStartAddress;
extern uint32_t g_bootFirmwareCrc;
extern uint8_t  g_bootRegionStatus[8];
extern int32_t  g_bootError;

/* ── API ────────────────────────────────────────────────────────── */
void        bcm_boot_init(void);
int32_t     bcm_boot_validate(void);
int32_t     bcm_boot_switch_slot(uint8_t slot);
const void *bcm_boot_get_flash_layout(uint8_t sector);
uint32_t    bcm_boot_get_fw_version(uint8_t slot);

#endif /* BCM_BOOT_H */
