/**
 * @file FiM.h
 * @brief Function Inhibition Manager — Suppress functions based on conditions
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full FiM driver is integrated.
 */

#ifndef FIM_H
#define FIM_H

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

typedef uint16_t FiM_FunctionIdType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FiM_Init(void);

extern Std_ReturnType FiM_DeInit(void);

extern void FiM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FiM_GetFunctionPermission(FiM_FunctionIdType FunctionId);

extern void FiM_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* FIM_H */
