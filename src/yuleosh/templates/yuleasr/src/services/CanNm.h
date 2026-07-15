/**
 * @file CanNm.h
 * @brief CAN Network Management — NM message handling for CAN (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef CANNM_SV_H
#define CANNM_SV_H

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

typedef uint8_t CanNm_StateType;
#define CANNM_STATE_BUS_SLEEP    0x00U
#define CANNM_STATE_PREPARE_BUS_SLEEP 0x01U
#define CANNM_STATE_NETWORK      0x02U

typedef uint8_t CanNm_PduIdType;
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanNm_Init(void);
extern Std_ReturnType CanNm_DeInit(void);
extern void CanNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void CanNm_MainFunction(void);
extern CanNm_StateType CanNm_GetState(uint8_t nmNodeId);
#ifdef __cplusplus
}
#endif

#endif /* CANNM_SV_H */
