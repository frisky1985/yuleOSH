/**
 * @file FrIf.h
 * @brief FlexRay Interface — FlexRay communication channel abstraction
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full FrIf driver is integrated.
 */

#ifndef FRIF_H
#define FRIF_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FrIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FrIf_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FrIf_Init(void);

extern Std_ReturnType FrIf_DeInit(void);

extern void FrIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FrIf_Transmit(PduIdType FrIfTxSduId, const PduInfoType *PduInfoPtr);

extern void FrIf_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* FRIF_H */
