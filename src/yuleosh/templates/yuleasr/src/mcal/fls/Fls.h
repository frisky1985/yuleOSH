/**
 * @file Fls.h
 * @brief Flash Driver — Sector erase, program, read
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Fls driver is integrated.
 */

#ifndef FLS_H
#define FLS_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Fls configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Fls_ConfigType;

typedef uint32_t Fls_AddressType;

typedef uint32_t Fls_LengthType;

typedef uint8_t Fls_StatusType;
#define FLS_IDLE     0x00U
#define FLS_BUSY     0x01U

typedef uint8_t Fls_JobResultType;
#define FLS_JOB_OK      0x00U
#define FLS_JOB_FAILED  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Fls_Init(const Fls_ConfigType *ConfigPtr);

extern Std_ReturnType Fls_DeInit(void);

extern void Fls_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Fls_Erase(Fls_AddressType TargetAddress, Fls_LengthType Length);

extern Std_ReturnType Fls_Write(Fls_AddressType TargetAddress, const uint8_t *SourceDataPtr, Fls_LengthType Length);

extern Std_ReturnType Fls_Read(Fls_AddressType SourceAddress, uint8_t *TargetDataPtr, Fls_LengthType Length);

extern Fls_StatusType Fls_GetStatus(void);

extern Fls_JobResultType Fls_GetJobResult(void);

extern void Fls_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* FLS_H */
