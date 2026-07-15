/**
 * @file LinSM.h
 * @brief LIN State Manager — LIN controller and transceiver state management (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef LINSM_SV_H
#define LINSM_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief LinSM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} LinSM_ConfigType;

typedef uint8_t LinSM_StateType;
#define LINSM_STATE_UNINIT  0x00U
#define LINSM_STATE_STARTED 0x01U
#define LINSM_STATE_STOPPED 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinSM_Init(void);
extern Std_ReturnType LinSM_DeInit(void);
extern void LinSM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinSM_RequestComMode(uint8_t ControllerId, uint8_t RequestedMode);
extern LinSM_StateType LinSM_GetControllerState(uint8_t ControllerId);
#ifdef __cplusplus
}
#endif

#endif /* LINSM_SV_H */
