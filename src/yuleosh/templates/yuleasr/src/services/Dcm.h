/**
 * @file Dcm.h
 * @brief Diagnostic Communication Manager — UDS request routing & processing
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef DCM_H
#define DCM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Dcm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Dcm_ConfigType;

typedef uint8_t Dcm_SessionType;
#define DCM_DEFAULT_SESSION  0x01U
#define DCM_EXTENDED_SESSION 0x02U
#define DCM_PROGRAMMING_SESSION 0x03U

typedef uint8_t Dcm_SecurityLevelType;
#define DCM_SEC_LOCKED   0x00U
#define DCM_SEC_UNLOCKED 0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Dcm_Init(void);
extern Std_ReturnType Dcm_DeInit(void);
extern void Dcm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void Dcm_MainFunction(void);
extern Std_ReturnType Dcm_RequestProcess(Dcm_OpStatusType opStatus);
extern Std_ReturnType Dcm_SetSession(Dcm_SessionType Session);
extern Dcm_SessionType Dcm_GetSession(void);
#ifdef __cplusplus
}
#endif

#endif /* DCM_H */
