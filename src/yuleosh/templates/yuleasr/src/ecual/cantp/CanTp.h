/**
 * @file CanTp.h
 * @brief CAN Transport Layer — ISO 15765-2 multi-frame segmentation
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full CanTp driver is integrated.
 */

#ifndef CANTP_H
#define CANTP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanTp_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanTp_Init(void);

extern Std_ReturnType CanTp_DeInit(void);

extern void CanTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanTp_Transmit(PduIdType CanTpTxSduId, const PduInfoType *PduInfoPtr);

extern Std_ReturnType CanTp_CancelTransmit(PduIdType CanTpTxSduId);

extern Std_ReturnType CanTp_CancelReceive(PduIdType CanTpRxSduId);

extern void CanTp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* CANTP_H */
