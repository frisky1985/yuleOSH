/**
 * @file SomeIpIf.h
 * @brief SOME/IP Interface — SOME/IP PDU routing between SoAd and Eth
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full SomeIpIf driver is integrated.
 */

#ifndef SOMEIPIF_H
#define SOMEIPIF_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief SomeIpIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} SomeIpIf_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType SomeIpIf_Init(void);

extern Std_ReturnType SomeIpIf_DeInit(void);

extern void SomeIpIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType SomeIpIf_Transmit(PduIdType SomeIpIfTxSduId, const PduInfoType *PduInfoPtr);

extern void SomeIpIf_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* SOMEIPIF_H */
