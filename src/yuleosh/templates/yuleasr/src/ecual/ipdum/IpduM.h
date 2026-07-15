/**
 * @file IpduM.h
 * @brief I-PDU Multiplexer — Multiplexed PDU routing
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full IpduM driver is integrated.
 */

#ifndef IPDUM_H
#define IPDUM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief IpduM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} IpduM_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType IpduM_Init(void);

extern Std_ReturnType IpduM_DeInit(void);

extern void IpduM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType IpduM_Transmit(PduIdType IpduMTxSduId, const PduInfoType *PduInfoPtr);

extern void IpduM_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* IPDUM_H */
