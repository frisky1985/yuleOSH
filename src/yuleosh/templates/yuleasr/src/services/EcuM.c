/**
 * @file EcuM.c
 * @brief ECU State Manager — Startup, shutdown, and sleep state control
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "EcuM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ECUM_Initialized = 0U;
static EcuM_StateType ECUM_CurrentState = ECUM_STATE_STARTUP;

/* ─── API implementations ─────────────────────────── */

/** @brief EcuM_Init — stub implementation */
Std_ReturnType EcuM_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    ECUM_Initialized = 1U;
    ECUM_CurrentState = ECUM_STATE_STARTUP;
    return E_OK;
}

/** @brief EcuM_DeInit — stub implementation */
Std_ReturnType EcuM_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    ECUM_Initialized = 0U;
    return E_OK;
}

/** @brief EcuM_GetVersionInfo — stub implementation */
void EcuM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief EcuM_SelectShutdownTarget — stub implementation */
void EcuM_SelectShutdownTarget(uint8_t ShutdownTarget)
{
    /* AUTOSAR stub — to be implemented */
    (void)ShutdownTarget;
}

/** @brief EcuM_GoSleep — stub implementation */
void EcuM_GoSleep(void)
{
    /* AUTOSAR stub — to be implemented */
    ECUM_CurrentState = ECUM_STATE_SLEEP;
}

/** @brief EcuM_GoHalt — stub implementation */
void EcuM_GoHalt(void)
{
    /* AUTOSAR stub — to be implemented */
    ECUM_CurrentState = ECUM_STATE_SHUTDOWN;
}

/** @brief EcuM_GetState — stub implementation */
EcuM_StateType EcuM_GetState(void)
{
    /* AUTOSAR stub — to be implemented */
    return ECUM_CurrentState;
}

/** @brief EcuM_StartupTwo — stub implementation */
void EcuM_StartupTwo(void)
{
    /* AUTOSAR stub — to be implemented */
    ECUM_CurrentState = ECUM_STATE_RUN;
}

/** @brief EcuM_MainFunction — stub implementation */
void EcuM_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
