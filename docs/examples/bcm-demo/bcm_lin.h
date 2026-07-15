/**
 * bcm_lin.h — BCM LIN Bus Driver Header
 */

#ifndef BCM_LIN_H
#define BCM_LIN_H

#include <stdint.h>
#include <stdbool.h>

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  linTxFrame[8];
extern uint8_t  linRxFrame[8];
extern uint32_t linMessageCount;
extern uint8_t  g_linBusError;
extern int32_t  g_linLastError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_lin_init(void);
int32_t  bcm_lin_send_frame(uint8_t id, const uint8_t *data, uint8_t dlc);
int32_t  bcm_lin_receive_frame(void *frame);
void     bcm_lin_process_incoming(uint8_t *data, uint32_t len);
int32_t  bcm_lin_configure_schedule(const uint8_t *schedule, uint32_t len);
int32_t  bcm_lin_execute_schedule(void);
void     bcm_lin_set_baud(uint32_t baud);

#endif /* BCM_LIN_H */

int32_t bcm_lin_handle_diag_request(uint8_t linId, uint8_t *buffer, uint32_t bufLen);
