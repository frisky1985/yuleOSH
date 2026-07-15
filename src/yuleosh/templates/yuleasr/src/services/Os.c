/**
 * @file Os.c
 * @brief AUTOSAR Operating System — Task and interrupt scheduling
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Os.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t OS_Initialized = 0U;
static Os_AppModeType OS_CurrentMode = OS_DEFAULT_APP_MODE;

/* ─── API implementations ─────────────────────────── */

/** @brief Os_Init — stub implementation */
Std_ReturnType Os_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    OS_Initialized = 1U;
    return E_OK;
}

/** @brief Os_DeInit — stub implementation */
Std_ReturnType Os_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    OS_Initialized = 0U;
    return E_OK;
}

/** @brief Os_GetVersionInfo — stub implementation */
void Os_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
{
    /* Stub — no version info available */
    if (VersionInfoPtr != NULL_PTR)
    {
        VersionInfoPtr->vendorID = 0U;
        VersionInfoPtr->moduleID = 0U;
        VersionInfoPtr->sw_major_version = 0U;
        VersionInfoPtr->sw_minor_version = 0U;
        VersionInfoPtr->sw_patch_version = 0U;
    }
}

/** @brief StartOS — stub implementation */
void StartOS(Os_AppModeType AppMode)
{
    /* AUTOSAR stub — to be implemented */
    OS_CurrentMode = AppMode;
}

/** @brief ShutdownOS — stub implementation */
void ShutdownOS(void)
{
    /* AUTOSAR stub — to be implemented */
}

/** @brief ActivateTask — stub implementation */
Std_ReturnType ActivateTask(Os_TaskType TaskId)
{
    /* AUTOSAR stub — to be implemented */
    (void)TaskId;
    return E_OK;
}

/** @brief TerminateTask — stub implementation */
Std_ReturnType TerminateTask(void)
{
    /* AUTOSAR stub — to be implemented */
    return E_OK;
}

/** @brief GetTaskState — stub implementation */
Os_TaskStateType GetTaskState(Os_TaskType TaskId, Os_TaskStateType *State)
{
    /* AUTOSAR stub — to be implemented */
    (void)TaskId;
    if (State != NULL_PTR)
    {
        *State = OS_TASK_READY;
    }
    return E_OK;
}

/** @brief SetRelAlarm — stub implementation */
Std_ReturnType SetRelAlarm(Os_AlarmType AlarmId, uint32_t Start, uint32_t Cycle)
{
    /* AUTOSAR stub — to be implemented */
    (void)AlarmId;
    (void)Start;
    (void)Cycle;
    return E_OK;
}

/** @brief CancelAlarm — stub implementation */
Std_ReturnType CancelAlarm(Os_AlarmType AlarmId)
{
    /* AUTOSAR stub — to be implemented */
    (void)AlarmId;
    return E_OK;
}
