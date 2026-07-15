/**
 * @file CanSm.c
 * @brief CAN State Manager — Controller state arbitration
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "CanSm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANSM_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanSm_Init — stub implementation */
Std_ReturnType CanSm_Init(void)
{
    CANSM_Initialized = 1U;
    return E_OK;
}

/** @brief CanSm_DeInit — stub implementation */
Std_ReturnType CanSm_DeInit(void)
{
    CANSM_Initialized = 0U;
    return E_OK;
}

/** @brief CanSm_GetVersionInfo — stub implementation */
void CanSm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief CanSm_RequestComMode — stub implementation */
Std_ReturnType CanSm_RequestComMode(uint8_t Network, CanSm_ComModeType ComMode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanSm_GetCurrentComMode — stub implementation */
CanSm_ComModeType CanSm_GetCurrentComMode(uint8_t Network)
{
    /* Stub — returning default */
    return CNSM_CM_OFF;
}

/** @brief CanSm_MainFunction — stub implementation */
void CanSm_MainFunction(void)
{
    /* Stub — no pending events */
}
