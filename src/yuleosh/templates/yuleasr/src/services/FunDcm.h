/**
 * @file FunDcm.h
 * @brief Functional DCM — Functional (non-physical) diagnostic request handler
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef FUNDCM_H
#define FUNDCM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FunDcm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FunDcm_ConfigType;

typedef uint8_t FunDcm_FuncAddrType;
#define FUNDCM_FUNC_ADDR_GLOBAL  0x00U
#define FUNDCM_FUNC_ADDR_GROUP   0x01U

typedef uint8_t FunDcm_StateType;
#define FUNDCM_STATE_IDLE    0x00U
#define FUNDCM_STATE_ACTIVE  0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FunDcm_Init(void);
extern Std_ReturnType FunDcm_DeInit(void);
extern void FunDcm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FunDcm_ProcessFuncRequest(const uint8_t *ReqData, uint16_t ReqLen, uint8_t *RespData, uint16_t *RespLen);
extern void FunDcm_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* FUNDCM_H */
