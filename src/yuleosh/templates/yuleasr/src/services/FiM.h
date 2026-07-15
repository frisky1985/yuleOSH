/**
 * @file FiM.h
 * @brief Function Inhibition Manager — Conditional function enable/disable (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef FIM_SV_H
#define FIM_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FiM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FiM_ConfigType;

typedef uint8_t FiM_FunctionIdType;
typedef uint8_t FiM_StatusType;
#define FIM_ENABLED  0x01U
#define FIM_DISABLED 0x00U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FiM_Init(void);
extern Std_ReturnType FiM_DeInit(void);
extern void FiM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern FiM_StatusType FiM_GetFunctionPermission(FiM_FunctionIdType FunctionId);
extern Std_ReturnType FiM_InhibitFunction(FiM_FunctionIdType FunctionId);
extern Std_ReturnType FiM_ReleaseFunction(FiM_FunctionIdType FunctionId);
#ifdef __cplusplus
}
#endif

#endif /* FIM_SV_H */
