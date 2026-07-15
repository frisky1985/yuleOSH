/**
 * @file CanSm.h
 * @brief CAN State Manager — Controller state arbitration
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full CanSm driver is integrated.
 */

#ifndef CANSM_H
#define CANSM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanSm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanSm_ConfigType;

typedef uint8_t CanSm_ComModeType;
#define CNSM_CM_OFF     0x00U
#define CNSM_CM_COMM    0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanSm_Init(void);

extern Std_ReturnType CanSm_DeInit(void);

extern void CanSm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanSm_RequestComMode(uint8_t Network, CanSm_ComModeType ComMode);

extern CanSm_ComModeType CanSm_GetCurrentComMode(uint8_t Network);

extern void CanSm_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* CANSM_H */
