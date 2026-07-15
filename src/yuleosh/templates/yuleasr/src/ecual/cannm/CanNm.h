/**
 * @file CanNm.h
 * @brief CAN Network Management — NM PDU coordination
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full CanNm driver is integrated.
 */

#ifndef CANNM_H
#define CANNM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanNm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanNm_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanNm_Init(void);

extern Std_ReturnType CanNm_DeInit(void);

extern void CanNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanNm_Transmit(PduIdType CanNmTxPduId, const PduInfoType *PduInfoPtr);

extern Std_ReturnType CanNm_NetworkRequest(uint8_t CanNmChannel);

extern Std_ReturnType CanNm_NetworkRelease(uint8_t CanNmChannel);

extern void CanNm_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* CANNM_H */
