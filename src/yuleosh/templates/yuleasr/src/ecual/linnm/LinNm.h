/**
 * @file LinNm.h
 * @brief LIN Network Management — LIN NM coordination
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full LinNm driver is integrated.
 */

#ifndef LINNM_H
#define LINNM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief LinNm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} LinNm_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinNm_Init(void);

extern Std_ReturnType LinNm_DeInit(void);

extern void LinNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinNm_NetworkRequest(uint8_t Channel);

extern Std_ReturnType LinNm_NetworkRelease(uint8_t Channel);

extern void LinNm_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* LINNM_H */
