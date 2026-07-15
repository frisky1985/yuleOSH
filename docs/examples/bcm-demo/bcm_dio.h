/**
 * bcm_dio.h — BCM Digital I/O Driver Header
 */

#ifndef BCM_DIO_H
#define BCM_DIO_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint32_t dioPinDirection;
extern uint32_t dioOutputValue;
extern uint16_t g_dioInputCapture;
extern int32_t  g_dioPortError;

/* ── API ────────────────────────────────────────────────────────── */
void    bcm_dio_init(void);
int32_t bcm_dio_configure_pin(uint8_t port, uint8_t pin, uint8_t mode, uint8_t pull);
void    bcm_dio_write_pin(uint8_t port, uint8_t pin, uint8_t value);
uint8_t bcm_dio_read_pin(uint8_t port, uint8_t pin);
void    bcm_dio_read_all(void);
void    bcm_dio_toggle_pin(uint8_t port, uint8_t pin);

#endif /* BCM_DIO_H */
