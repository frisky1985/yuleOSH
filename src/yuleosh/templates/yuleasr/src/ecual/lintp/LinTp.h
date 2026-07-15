/**
 * @file LinTp.h
 * @brief LIN Transport Layer — LIN diagnostic transport
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full LinTp driver is integrated.
 */

#ifndef LINTP_H
#define LINTP_H

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

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinTp_Init(void);

extern Std_ReturnType LinTp_DeInit(void);

extern void LinTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinTp_Transmit(PduIdType LinTpTxSduId, const PduInfoType *PduInfoPtr);

extern void LinTp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* LINTP_H */
