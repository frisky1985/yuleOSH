/**
 * @file FrTp.h
 * @brief FlexRay Transport Layer — ISO 10681-2 segmentation
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full FrTp driver is integrated.
 */

#ifndef FRTP_H
#define FRTP_H

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

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FrTp_Init(void);

extern Std_ReturnType FrTp_DeInit(void);

extern void FrTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FrTp_Transmit(PduIdType FrTpTxSduId, const PduInfoType *PduInfoPtr);

extern void FrTp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* FRTP_H */
