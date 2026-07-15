/**
 * @file E2E.h
 * @brief End-to-End Communication Protection — Data integrity & freshness for safety-critical PDUs
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef E2E_H
#define E2E_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief E2E configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} E2E_ConfigType;

typedef uint8_t E2E_ProfileType;
#define E2E_PROFILE_1  0x01U
#define E2E_PROFILE_2  0x02U
#define E2E_PROFILE_4  0x04U
#define E2E_PROFILE_5  0x05U
#define E2E_PROFILE_6  0x06U
#define E2E_PROFILE_11 0x0BU
#define E2E_PROFILE_22 0x16U

typedef uint8_t E2E_StateType;
#define E2E_STATE_IDLE      0x00U
#define E2E_STATE_OK        0x01U
#define E2E_STATE_ERROR     0x02U

typedef uint8_t E2E_StatusType;
#define E2E_STATUS_OK          0x00U
#define E2E_STATUS_ERROR       0x01U
#define E2E_STATUS_REPEATED    0x02U
#define E2E_STATUS_WRONG_SEQ   0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType E2E_Init(void);
extern Std_ReturnType E2E_DeInit(void);
extern void E2E_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType E2E_Protect(E2E_ProfileType Profile, uint8_t *Data, uint16_t Length);
extern Std_ReturnType E2E_Check(E2E_ProfileType Profile, const uint8_t *Data, uint16_t Length);
extern void E2E_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* E2E_H */
