/**
 * @file Mcu.c
 * @brief MCU Driver — Clock/PLL/Reset/Mode management
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Mcu.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t MCU_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Mcu_Init — stub implementation */
Std_ReturnType Mcu_Init(const Mcu_ConfigType *ConfigPtr)
{
    MCU_Initialized = 1U;
    return E_OK;
}

/** @brief Mcu_DeInit — stub implementation */
Std_ReturnType Mcu_DeInit(void)
{
    MCU_Initialized = 0U;
    return E_OK;
}

/** @brief Mcu_GetVersionInfo — stub implementation */
void Mcu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Mcu_SetMode — stub implementation */
Std_ReturnType Mcu_SetMode(Mcu_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Mcu_GetResetReason — stub implementation */
Std_ReturnType Mcu_GetResetReason(Mcu_ResetType *ResetReason)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Mcu_PerformReset — stub implementation */
void Mcu_PerformReset(void)
{
    /* Stub — no operation */
}

/** @brief Mcu_InitClock — stub implementation */
Std_ReturnType Mcu_InitClock(const Mcu_ClockType *ClockSetting)
{
    /* Stub — returning default */
    return E_OK;
}
