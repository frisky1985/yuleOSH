/**
 * @file Srp.h
 * @brief Synchronous Real-time Protocol — Time-synchronized data exchange
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Srp driver is integrated.
 */

#ifndef SRP_H
#define SRP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Srp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Srp_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Srp_Init(void);

extern Std_ReturnType Srp_DeInit(void);

extern void Srp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Srp_Transmit(PduIdType SrpTxSduId, const PduInfoType *PduInfoPtr);

extern void Srp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* SRP_H */
