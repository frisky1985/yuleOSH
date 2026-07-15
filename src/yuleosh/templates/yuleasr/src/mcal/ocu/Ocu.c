/**
 * @file Ocu.c
 * @brief OCU Driver — Output Compare
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Ocu.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t OCU_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Ocu_Init — stub implementation */
Std_ReturnType Ocu_Init(const Ocu_ConfigType *ConfigPtr)
{
    OCU_Initialized = 1U;
    return E_OK;
}

/** @brief Ocu_DeInit — stub implementation */
Std_ReturnType Ocu_DeInit(void)
{
    OCU_Initialized = 0U;
    return E_OK;
}

/** @brief Ocu_GetVersionInfo — stub implementation */
void Ocu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Ocu_EnableOutputCompare — stub implementation */
Std_ReturnType Ocu_EnableOutputCompare(Ocu_ChannelType Channel, Ocu_CompareValueType Value)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Ocu_DisableOutputCompare — stub implementation */
Std_ReturnType Ocu_DisableOutputCompare(Ocu_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Ocu_SetCompareValue — stub implementation */
Std_ReturnType Ocu_SetCompareValue(Ocu_ChannelType Channel, Ocu_CompareValueType Value)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Ocu_GetCompareValue — stub implementation */
Ocu_CompareValueType Ocu_GetCompareValue(Ocu_ChannelType Channel)
{
    /* Stub — returning default */
    return 0U;
}
