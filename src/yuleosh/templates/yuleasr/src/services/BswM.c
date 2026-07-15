/**
 * @file BswM.c
 * @brief BSW Mode Manager — Mode arbitration and mode request aggregation
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "BswM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t BSWM_Initialized = 0U;
static BswM_ModeType BSWM_CurrentMode = BSWM_MODE_STARTUP;

/* ─── API implementations ─────────────────────────── */

/** @brief BswM_Init — stub implementation */
Std_ReturnType BswM_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    BSWM_Initialized = 1U;
    BSWM_CurrentMode = BSWM_MODE_STARTUP;
    return E_OK;
}

/** @brief BswM_DeInit — stub implementation */
Std_ReturnType BswM_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    BSWM_Initialized = 0U;
    return E_OK;
}

/** @brief BswM_GetVersionInfo — stub implementation */
void BswM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief BswM_RequestMode — stub implementation */
Std_ReturnType BswM_RequestMode(BswM_ModeType Mode)
{
    /* AUTOSAR stub — to be implemented */
    BSWM_CurrentMode = Mode;
    return E_OK;
}

/** @brief BswM_GetCurrentMode — stub implementation */
BswM_ModeType BswM_GetCurrentMode(void)
{
    /* AUTOSAR stub — to be implemented */
    return BSWM_CurrentMode;
}

/** @brief BswM_MainFunction — stub implementation */
void BswM_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
