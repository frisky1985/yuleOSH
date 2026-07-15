/**
 * @file SomeIpTp.h
 * @brief SOME/IP Transport Protocol — SOME/IP segmentation and reassembly
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef SOMEIPTP_H
#define SOMEIPTP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief SomeIpTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} SomeIpTp_ConfigType;

typedef uint8_t SomeIpTp_StateType;
#define SOMEIPTP_STATE_IDLE       0x00U
#define SOMEIPTP_STATE_TX         0x01U
#define SOMEIPTP_STATE_RX         0x02U
#define SOMEIPTP_STATE_TF_WAIT    0x03U

typedef uint8_t SomeIpTp_ProtocolType;
#define SOMEIPTP_TP_UDP  0x00U
#define SOMEIPTP_TP_TCP  0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType SomeIpTp_Init(void);
extern Std_ReturnType SomeIpTp_DeInit(void);
extern void SomeIpTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType SomeIpTp_Transmit(PduIdType SomeIpTpTxSduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType SomeIpTp_CancelTransmit(PduIdType SomeIpTpTxSduId);
extern void SomeIpTp_MainFunction(void);
extern Std_ReturnType SomeIpTp_GetState(uint8_t ChannelId, SomeIpTp_StateType *State);
#ifdef __cplusplus
}
#endif

#endif /* SOMEIPTP_H */
