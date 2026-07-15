/**
 * @file LinSM.h
 * @brief LIN Schedule Manager — Schedule table arbitration
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full LinSM driver is integrated.
 */

#ifndef LINSM_H
#define LINSM_H

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

typedef uint8_t LinSM_ScheduleType;
#define LINSM_SCHEDULE_NONE  0x00U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinSM_Init(void);

extern Std_ReturnType LinSM_DeInit(void);

extern void LinSM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinSM_RequestSchedule(uint8_t Channel, LinSM_ScheduleType Schedule);

extern LinSM_ScheduleType LinSM_GetCurrentSchedule(uint8_t Channel);

extern void LinSM_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* LINSM_H */
