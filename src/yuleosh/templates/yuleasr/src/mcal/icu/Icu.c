/**
 * @file Icu.c
 * @brief ICU Driver — Input Capture (period/pulse width/edge)
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Icu.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ICU_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Icu_Init — stub implementation */
Std_ReturnType Icu_Init(const Icu_ConfigType *ConfigPtr)
{
    ICU_Initialized = 1U;
    return E_OK;
}

/** @brief Icu_DeInit — stub implementation */
Std_ReturnType Icu_DeInit(void)
{
    ICU_Initialized = 0U;
    return E_OK;
}

/** @brief Icu_GetVersionInfo — stub implementation */
void Icu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Icu_StartSignalMeasurement — stub implementation */
Std_ReturnType Icu_StartSignalMeasurement(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Icu_StopSignalMeasurement — stub implementation */
Std_ReturnType Icu_StopSignalMeasurement(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Icu_GetTimeElapsed — stub implementation */
Icu_TimeType Icu_GetTimeElapsed(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return 0U;
}

/** @brief Icu_GetDutyCycle — stub implementation */
Icu_DutyCycleType Icu_GetDutyCycle(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return {0U, 0U};
}

/** @brief Icu_EnableEdgeNotification — stub implementation */
Std_ReturnType Icu_EnableEdgeNotification(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Icu_DisableEdgeNotification — stub implementation */
Std_ReturnType Icu_DisableEdgeNotification(Icu_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}
