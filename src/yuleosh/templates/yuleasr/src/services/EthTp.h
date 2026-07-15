/**
 * @file EthTp.h
 * @brief Ethernet Transport Protocol — Segmentation and reassembly for Ethernet frames
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef ETHTP_H
#define ETHTP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief EthTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} EthTp_ConfigType;

typedef uint8_t EthTp_StateType;
#define ETHTP_STATE_IDLE     0x00U
#define ETHTP_STATE_TX       0x01U
#define ETHTP_STATE_RX       0x02U
#define ETHTP_STATE_WAITING  0x03U

typedef uint8_t EthTp_ChannelType;
#define ETHTP_CHANNEL_0  0x00U
#define ETHTP_CHANNEL_1  0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType EthTp_Init(void);
extern Std_ReturnType EthTp_DeInit(void);
extern void EthTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType EthTp_Transmit(PduIdType EthTpTxSduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType EthTp_CancelTransmit(PduIdType EthTpTxSduId);
extern void EthTp_MainFunction(void);
extern void EthTp_RxIndication(PduIdType pduId);
extern void EthTp_TxConfirmation(PduIdType pduId);
#ifdef __cplusplus
}
#endif

#endif /* ETHTP_H */
