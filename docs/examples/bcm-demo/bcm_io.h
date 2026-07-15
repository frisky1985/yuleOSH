/**
 * bcm_io.h — BCM I/O Manager Header
 */

#ifndef BCM_IO_H
#define BCM_IO_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  ioOutputState[32];
extern uint16_t ioInputState;
extern uint8_t  g_ioFaultRegister;
extern int32_t  g_ioLastError;

/* ── API ────────────────────────────────────────────────────────── */
void    bcm_io_init(void);
void    bcm_io_enable_outputs(void);
void    bcm_io_disable_outputs(void);
void    bcm_io_set_output(uint8_t pin, uint8_t level);
uint8_t bcm_io_read_input(uint8_t pin);
void    bcm_io_set_pwm(uint8_t channel, uint8_t dutyPercent);
void    bcm_io_read_all(void);

#endif /* BCM_IO_H */
