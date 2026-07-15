/**
 * @file CanTp.h
 * @brief CAN Transport Protocol — Segmentation and reassembly for CAN (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef CANTP_SV_H
#define CANTP_SV_H

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

typedef uint8_t CanTp_StateType;
#define CANTP_STATE_IDLE  0x00U
#define CANTP_STATE_SF    0x01U
#define CANTP_STATE_FF    0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanTp_Init(void);
extern Std_ReturnType CanTp_DeInit(void);
extern void CanTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanTp_Transmit(PduIdType CanTpTxSduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType CanTp_CancelTransmit(PduIdType CanTpTxSduId);
extern void CanTp_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* CANTP_SV_H */
