/**
 * @file FrNm.h
 * @brief FlexRay Network Management — NM message handling for FlexRay
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef FRNM_H
#define FRNM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FrNm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FrNm_ConfigType;

typedef uint8_t FrNm_StateType;
#define FRNM_STATE_BUS_SLEEP    0x00U
#define FRNM_STATE_PREPARE_BUS_SLEEP 0x01U
#define FRNM_STATE_NETWORK      0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FrNm_Init(void);
extern Std_ReturnType FrNm_DeInit(void);
extern void FrNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void FrNm_MainFunction(void);
extern FrNm_StateType FrNm_GetState(uint8_t nmNodeId);
extern Std_ReturnType FrNm_NetworkRequest(void);
#ifdef __cplusplus
}
#endif

#endif /* FRNM_H */
