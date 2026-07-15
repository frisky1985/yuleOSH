/**
 * @file LinIf.h
 * @brief LIN Interface — PDU routing between LIN driver and upper layers (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef LINIF_SV_H
#define LINIF_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief LinIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} LinIf_ConfigType;

typedef uint8_t LinIf_ControllerModeType;
#define LINIF_CS_UNINIT  0x00U
#define LINIF_CS_STARTED 0x01U
#define LINIF_CS_STOPPED 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinIf_Init(void);
extern Std_ReturnType LinIf_DeInit(void);
extern void LinIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinIf_SetControllerMode(uint8_t ControllerId, LinIf_ControllerModeType Mode);
extern Std_ReturnType LinIf_ScheduleRequest(uint8_t Channel, uint8_t ScheduleIndex);
extern void LinIf_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* LINIF_SV_H */
