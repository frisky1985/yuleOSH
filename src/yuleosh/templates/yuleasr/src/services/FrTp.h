/**
 * @file FrTp.h
 * @brief FlexRay Transport Protocol — Segmentation and reassembly for FlexRay (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef FRTP_SV_H
#define FRTP_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FrTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FrTp_ConfigType;

typedef uint8_t FrTp_StateType;
#define FRTP_STATE_IDLE  0x00U
#define FRTP_STATE_RX    0x01U
#define FRTP_STATE_TX    0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FrTp_Init(void);
extern Std_ReturnType FrTp_DeInit(void);
extern void FrTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FrTp_Transmit(PduIdType FrTpTxSduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType FrTp_CancelTransmit(PduIdType FrTpTxSduId);
extern void FrTp_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* FRTP_SV_H */
