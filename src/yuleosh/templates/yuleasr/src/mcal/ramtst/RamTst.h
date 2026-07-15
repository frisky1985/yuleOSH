/**
 * @file RamTst.h
 * @brief RAM Test Driver — March C-/Galpat RAM self-test
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full RamTst driver is integrated.
 */

#ifndef RAMTST_H
#define RAMTST_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief RamTst configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} RamTst_ConfigType;

typedef uint8_t RamTst_AreaType;
#define RAMTST_AREA_ALL    0x00U
#define RAMTST_AREA_STACK  0x01U

typedef uint8_t RamTst_AlgorithmType;
#define RAMTST_ALGO_MARCH_C  0x00U
#define RAMTST_ALGO_GALPAT   0x01U

typedef struct { uint8_t passed; uint32_t failedAddr; uint32_t expected; uint32_t actual; } RamTst_TestResultType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType RamTst_Init(const RamTst_ConfigType *ConfigPtr);

extern Std_ReturnType RamTst_DeInit(void);

extern void RamTst_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType RamTst_StartTest(RamTst_AreaType Area, RamTst_AlgorithmType Algorithm);

extern Std_ReturnType RamTst_GetResult(RamTst_AreaType Area, RamTst_TestResultType *ResultPtr);

extern Std_ReturnType RamTst_StopTest(RamTst_AreaType Area);

extern void RamTst_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* RAMTST_H */
