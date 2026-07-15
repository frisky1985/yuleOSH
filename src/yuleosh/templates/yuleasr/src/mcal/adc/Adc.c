/**
 * @file Adc.c
 * @brief ADC Driver — 12-bit SAR ADC with HW trigger
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Adc.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ADC_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Adc_Init — stub implementation */
Std_ReturnType Adc_Init(const Adc_ConfigType *ConfigPtr)
{
    ADC_Initialized = 1U;
    return E_OK;
}

/** @brief Adc_DeInit — stub implementation */
Std_ReturnType Adc_DeInit(void)
{
    ADC_Initialized = 0U;
    return E_OK;
}

/** @brief Adc_GetVersionInfo — stub implementation */
void Adc_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Adc_StartGroupConversion — stub implementation */
Std_ReturnType Adc_StartGroupConversion(Adc_GroupType Group)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Adc_StopGroupConversion — stub implementation */
Std_ReturnType Adc_StopGroupConversion(Adc_GroupType Group)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Adc_ReadGroup — stub implementation */
Std_ReturnType Adc_ReadGroup(Adc_GroupType Group, Adc_ValueGroupType *DataBufferPtr)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief Adc_GetGroupStatus — stub implementation */
Adc_GroupStatusType Adc_GetGroupStatus(Adc_GroupType Group)
{
    /* Stub — returning default */
    return ADC_NOT_INIT;
}
