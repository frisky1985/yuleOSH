/**
 * @file LinNm.h
 * @brief LIN Network Management — NM message handling for LIN (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef LINNM_SV_H
#define LINNM_SV_H

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

typedef uint8_t LinNm_StateType;
#define LINNM_STATE_BUS_SLEEP    0x00U
#define LINNM_STATE_NETWORK      0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinNm_Init(void);
extern Std_ReturnType LinNm_DeInit(void);
extern void LinNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void LinNm_MainFunction(void);
extern LinNm_StateType LinNm_GetState(uint8_t nmNodeId);
#ifdef __cplusplus
}
#endif

#endif /* LINNM_SV_H */
