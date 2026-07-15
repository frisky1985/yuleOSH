/**
 * @file Wdg.c
 * @brief Watchdog Driver — Internal watchdog timeout/trigger
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Wdg.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t WDG_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Wdg_Init — stub implementation */
Std_ReturnType Wdg_Init(const Wdg_ConfigType *ConfigPtr)
{
    WDG_Initialized = 1U;
    return E_OK;
}

/** @brief Wdg_DeInit — stub implementation */
Std_ReturnType Wdg_DeInit(void)
{
    WDG_Initialized = 0U;
    return E_OK;
}

/** @brief Wdg_GetVersionInfo — stub implementation */
void Wdg_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Wdg_SetTriggerCondition — stub implementation */
Std_ReturnType Wdg_SetTriggerCondition(uint16_t TimeoutMs)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Wdg_SetMode — stub implementation */
Std_ReturnType Wdg_SetMode(Wdg_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Wdg_GetMode — stub implementation */
Wdg_ModeType Wdg_GetMode(void)
{
    /* Stub — returning default */
    return WDGIF_OFF_MODE;
}
