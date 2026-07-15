/**
 * @file Os.h
 * @brief AUTOSAR Operating System — Task and interrupt scheduling
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef OS_H
#define OS_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Os configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Os_ConfigType;

typedef uint8_t Os_TaskType;
typedef uint8_t Os_AlarmType;
typedef uint8_t Os_TaskStateType;
#define OS_TASK_READY    0x00U
#define OS_TASK_RUNNING  0x01U
#define OS_TASK_WAITING  0x02U
#define OS_TASK_SUSPENDED 0x03U

typedef uint8_t Os_AppModeType;
#define OS_DEFAULT_APP_MODE 0x01U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Os_Init(void);
extern Std_ReturnType Os_DeInit(void);
extern void Os_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern void StartOS(Os_AppModeType AppMode);
extern void ShutdownOS(void);
extern Std_ReturnType ActivateTask(Os_TaskType TaskId);
extern Std_ReturnType TerminateTask(void);
extern Os_TaskStateType GetTaskState(Os_TaskType TaskId, Os_TaskStateType *State);
extern Std_ReturnType SetRelAlarm(Os_AlarmType AlarmId, uint32_t Start, uint32_t Cycle);
extern Std_ReturnType CancelAlarm(Os_AlarmType AlarmId);
#ifdef __cplusplus
}
#endif

#endif /* OS_H */
