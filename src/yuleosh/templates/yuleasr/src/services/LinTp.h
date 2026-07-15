/**
 * @file LinTp.h
 * @brief LIN Transport Protocol — Segmentation and reassembly for LIN (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef LINTP_SV_H
#define LINTP_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief LinTp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} LinTp_ConfigType;

typedef uint8_t LinTp_StateType;
#define LINTP_STATE_IDLE  0x00U
#define LINTP_STATE_RX    0x01U
#define LINTP_STATE_TX    0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinTp_Init(void);
extern Std_ReturnType LinTp_DeInit(void);
extern void LinTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinTp_Transmit(PduIdType LinTpTxSduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType LinTp_CancelTransmit(PduIdType LinTpTxSduId);
extern void LinTp_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* LINTP_SV_H */
