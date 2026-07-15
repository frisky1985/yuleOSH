/**
 * @file SchM.h
 * @brief Schedule Manager — Runnable and task scheduling
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef SCHM_H
#define SCHM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief SchM configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} SchM_ConfigType;

typedef uint8_t SchM_TaskType;
#define SCHM_TASK_1MS  0x00U
#define SCHM_TASK_10MS 0x01U
#define SCHM_TASK_100MS 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType SchM_Init(void);
extern Std_ReturnType SchM_DeInit(void);
extern void SchM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void SchM_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* SCHM_H */
