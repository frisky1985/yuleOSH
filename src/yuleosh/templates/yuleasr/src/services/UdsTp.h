/**
 * @file UdsTp.h
 * @brief UDS Transport Protocol — ISO 15765-2 CAN transport layer for UDS
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef UDSTP_H
#define UDSTP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief UdsTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} UdsTp_ConfigType;

typedef uint8_t UdsTp_StateType;
#define UDSTP_STATE_IDLE   0x00U
#define UDSTP_STATE_TX     0x01U
#define UDSTP_STATE_RX     0x02U
#define UDSTP_STATE_WAIT   0x03U

typedef uint8_t UdsTp_ProtocolType;
#define UDSTP_PROTOCOL_CAN    0x00U
#define UDSTP_PROTOCOL_LIN    0x01U
#define UDSTP_PROTOCOL_FR     0x02U
#define UDSTP_PROTOCOL_ETH    0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType UdsTp_Init(void);
extern Std_ReturnType UdsTp_DeInit(void);
extern void UdsTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType UdsTp_Transmit(const uint8_t *Data, uint16_t Length, UdsTp_ProtocolType Protocol);
extern Std_ReturnType UdsTp_CancelTransmit(void);
extern void UdsTp_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* UDSTP_H */
