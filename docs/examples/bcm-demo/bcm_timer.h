/**
 * bcm_timer.h — BCM Timer Manager Header
 */

#ifndef BCM_TIMER_H
#define BCM_TIMER_H

#include <stdint.h>
#include <stdbool.h>

/* ── Timer callback type ──────────────────────────────────────────── */
typedef void (*TimerCallback)(uint8_t timerId);

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t timerOverflowCount;
extern uint32_t g_timerCaptureVal[8];
extern uint8_t  g_timerStatus;
extern int32_t  g_timerError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_timer_init(void);
int32_t  bcm_timer_start(uint8_t timerId, uint32_t periodUs, TimerCallback callback);
int32_t  bcm_timer_stop(uint8_t timerId);
void     bcm_timer_irq_handler(uint8_t timerId);
int32_t  bcm_timer_configure_pwm(uint8_t timerId, uint8_t channel, uint16_t frequencyHz, uint8_t dutyPercent);
uint32_t bcm_timer_read_counter(uint8_t timerId);

#endif /* BCM_TIMER_H */
