/**
 * @file LinIf.h
 * @brief LIN Interface — Schedule table and frame routing
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full LinIf driver is integrated.
 */

#ifndef LINIF_H
#define LINIF_H

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

typedef uint8_t LinIf_ScheduleType;
#define LINIF_SCHEDULE_NONE  0x00U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinIf_Init(void);

extern Std_ReturnType LinIf_DeInit(void);

extern void LinIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinIf_SetSchedule(uint8_t Channel, LinIf_ScheduleType Schedule);

extern LinIf_ScheduleType LinIf_GetSchedule(uint8_t Channel);

extern Std_ReturnType LinIf_Transmit(PduIdType LinIfTxSduId, const PduInfoType *PduInfoPtr);

extern void LinIf_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* LINIF_H */
