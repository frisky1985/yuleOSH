/**
 * bcm_comm.h — BCM Communication Manager Header
 */

#ifndef BCM_COMM_H
#define BCM_COMM_H

#include <stdint.h>
#include <stdbool.h>

/* ── Message IDs ────────────────────────────────────────────────── */
typedef enum {
    BCM_MSG_NONE         = 0x00,
    BCM_MSG_HEARTBEAT    = 0x01,
    BCM_MSG_SHUTDOWN     = 0x02,
    BCM_MSG_WAKEUP       = 0x03,
    BCM_MSG_DIAG_REQ     = 0x10,
    BCM_MSG_DIAG_RESP    = 0x11,
    BCM_MSG_DIAG_MODE    = 0x12,
    BCM_MSG_FAULT_ALERT  = 0x20,
    BCM_MSG_POWER_STATE  = 0x30,
    BCM_MSG_SENSOR_DATA  = 0x40,
    BCM_MSG_ACTUATOR_CMD = 0x50,
    BCM_MSG_CONFIG_UPD   = 0x60,
    BCM_MSG_LIN_DATA     = 0x70,
} BcmMessageId;

/* ── Extern globals ─────────────────────────────────────────────── */
extern uint8_t  commTxBuffer[64];
extern uint32_t commMessageSent;
extern uint8_t  g_commErrorFlags;
extern int32_t  g_commLastError;

/* ── API ────────────────────────────────────────────────────────── */
void     bcm_comm_init(void);
int32_t  bcm_comm_broadcast(BcmMessageId msgId);
int32_t  bcm_comm_receive(const uint8_t *frame, uint32_t frameLen);
uint32_t bcm_comm_get_queue_count(void);

#endif /* BCM_COMM_H */
