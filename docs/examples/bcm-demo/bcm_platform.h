/**
 * bcm_platform.h — BCM Platform Abstraction Header
 */

#ifndef BCM_PLATFORM_H
#define BCM_PLATFORM_H

#include <stdint.h>
#include <stdbool.h>

/* ── Reset causes ────────────────────────────────────────────────── */
#define RESET_CAUSE_POR        0x01U
#define RESET_CAUSE_PIN        0x02U
#define RESET_CAUSE_WATCHDOG   0x04U
#define RESET_CAUSE_SOFTWARE   0x08U
#define RESET_CAUSE_LOW_POWER  0x10U

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t platformResetCause;
extern uint32_t g_platformClockSpeed;
extern uint8_t  g_platformCpuId[12];
extern int32_t  g_platformError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_platform_init(void);
uint32_t bcm_platform_get_uptime_ms(void);
void     bcm_platform_tick_1ms(void);
void     bcm_platform_reset(void);
void     bcm_platform_sleep(void);
void     bcm_platform_deep_sleep(void);

/* ── Compiler barrier ────────────────────────────────────────────── */
#ifndef __asm
#define __asm(asm_str)          /* stub for build without GCC */
#endif

#endif /* BCM_PLATFORM_H */
