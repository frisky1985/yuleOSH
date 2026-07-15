/**
 * @file WdgIf.c
 * @brief Watchdog Interface — Abstract internal/external watchdog access
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "WdgIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t WDGIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief WdgIf_Init — stub implementation */
Std_ReturnType WdgIf_Init(void)
{
    WDGIF_Initialized = 1U;
    return E_OK;
}

/** @brief WdgIf_DeInit — stub implementation */
Std_ReturnType WdgIf_DeInit(void)
{
    WDGIF_Initialized = 0U;
    return E_OK;
}

/** @brief WdgIf_GetVersionInfo — stub implementation */
void WdgIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief WdgIf_SetTriggerCondition — stub implementation */
Std_ReturnType WdgIf_SetTriggerCondition(uint8_t DeviceIndex, uint16_t TimeoutMs)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief WdgIf_SetMode — stub implementation */
Std_ReturnType WdgIf_SetMode(uint8_t DeviceIndex, WdgIf_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief WdgIf_GetMode — stub implementation */
WdgIf_ModeType WdgIf_GetMode(uint8_t DeviceIndex)
{
    /* Stub — returning default */
    return WDGIF_OFF_MODE;
}
