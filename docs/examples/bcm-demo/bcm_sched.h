/**
 * bcm_sched.h — BCM Scheduler Header
 */

#ifndef BCM_SCHED_H
#define BCM_SCHED_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t schedulerTickCount;
extern uint8_t  g_schedTaskCount;
extern int32_t  g_schedOverrun;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_sched_init(void);
int32_t  bcm_sched_register_task(const char *name, void (*func)(void), uint32_t intervalMs);
void     bcm_sched_tick(uint32_t currentMs);
void     bcm_sched_start(void);
void     bcm_sched_stop(void);

#endif /* BCM_SCHED_H */
