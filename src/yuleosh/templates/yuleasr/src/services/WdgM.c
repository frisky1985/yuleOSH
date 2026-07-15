/**
 * @file WdgM.c
 * @brief Watchdog Manager — Supervised entity deadline monitoring
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "WdgM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t WDGM_Initialized = 0U;
static WdgM_ModeType WDGM_CurrentMode = WDGM_MODE_OFF;

/* ─── API implementations ─────────────────────────── */

/** @brief WdgM_Init — stub implementation */
Std_ReturnType WdgM_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    WDGM_Initialized = 1U;
    WDGM_CurrentMode = WDGM_MODE_OFF;
    return E_OK;
}

/** @brief WdgM_DeInit — stub implementation */
Std_ReturnType WdgM_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    WDGM_Initialized = 0U;
    return E_OK;
}

/** @brief WdgM_GetVersionInfo — stub implementation */
void WdgM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief WdgM_SetMode — stub implementation */
Std_ReturnType WdgM_SetMode(WdgM_ModeType Mode)
{
    /* AUTOSAR stub — to be implemented */
    WDGM_CurrentMode = Mode;
    return E_OK;
}

/** @brief WdgM_PerformReset — stub implementation */
Std_ReturnType WdgM_PerformReset(void)
{
    /* AUTOSAR stub — to be implemented */
    return E_OK;
}

/** @brief WdgM_AlarmNotification — stub implementation */
void WdgM_AlarmNotification(uint8_t seId)
{
    /* AUTOSAR stub — to be implemented */
    (void)seId;
}
