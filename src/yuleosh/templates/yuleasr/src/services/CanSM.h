/**
 * @file CanSM.h
 * @brief CAN State Manager — CAN controller and transceiver state management (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef CANSM_SV_H
#define CANSM_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanSM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanSM_ConfigType;

typedef uint8_t CanSM_StateType;
#define CANSM_STATE_UNINIT    0x00U
#define CANSM_STATE_STARTED   0x01U
#define CANSM_STATE_STOPPED   0x02U
#define CANSM_STATE_SLEEP     0x03U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanSM_Init(void);
extern Std_ReturnType CanSM_DeInit(void);
extern void CanSM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanSM_RequestComMode(uint8_t ControllerId, uint8_t RequestedMode);
extern CanSM_StateType CanSM_GetControllerState(uint8_t ControllerId);
#ifdef __cplusplus
}
#endif

#endif /* CANSM_SV_H */
