/**
 * @file Eep.c
 * @brief EEPROM Driver — External EEPROM read/write/erase
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Eep.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t EEP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Eep_Init — stub implementation */
Std_ReturnType Eep_Init(const Eep_ConfigType *ConfigPtr)
{
    EEP_Initialized = 1U;
    return E_OK;
}

/** @brief Eep_DeInit — stub implementation */
Std_ReturnType Eep_DeInit(void)
{
    EEP_Initialized = 0U;
    return E_OK;
}

/** @brief Eep_GetVersionInfo — stub implementation */
void Eep_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Eep_Read — stub implementation */
Std_ReturnType Eep_Read(Eep_AddressType TargetAddress, uint8_t *TargetDataPtr, Eep_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eep_Write — stub implementation */
Std_ReturnType Eep_Write(Eep_AddressType TargetAddress, const uint8_t *SourceDataPtr, Eep_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eep_Erase — stub implementation */
Std_ReturnType Eep_Erase(Eep_AddressType TargetAddress, Eep_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eep_GetStatus — stub implementation */
Eep_StatusType Eep_GetStatus(void)
{
    /* Stub — returning default */
    return EEP_IDLE;
}

/** @brief Eep_MainFunction — stub implementation */
void Eep_MainFunction(void)
{
    /* Stub — no pending events */
}
