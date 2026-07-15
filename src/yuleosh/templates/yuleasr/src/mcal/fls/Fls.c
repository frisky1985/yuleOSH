/**
 * @file Fls.c
 * @brief Flash Driver — Sector erase, program, read
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Fls.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FLS_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Fls_Init — stub implementation */
Std_ReturnType Fls_Init(const Fls_ConfigType *ConfigPtr)
{
    FLS_Initialized = 1U;
    return E_OK;
}

/** @brief Fls_DeInit — stub implementation */
Std_ReturnType Fls_DeInit(void)
{
    FLS_Initialized = 0U;
    return E_OK;
}

/** @brief Fls_GetVersionInfo — stub implementation */
void Fls_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Fls_Erase — stub implementation */
Std_ReturnType Fls_Erase(Fls_AddressType TargetAddress, Fls_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fls_Write — stub implementation */
Std_ReturnType Fls_Write(Fls_AddressType TargetAddress, const uint8_t *SourceDataPtr, Fls_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fls_Read — stub implementation */
Std_ReturnType Fls_Read(Fls_AddressType SourceAddress, uint8_t *TargetDataPtr, Fls_LengthType Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fls_GetStatus — stub implementation */
Fls_StatusType Fls_GetStatus(void)
{
    /* Stub — returning default */
    return FLS_IDLE;
}

/** @brief Fls_GetJobResult — stub implementation */
Fls_JobResultType Fls_GetJobResult(void)
{
    /* Stub — returning default */
    return FLS_JOB_OK;
}

/** @brief Fls_MainFunction — stub implementation */
void Fls_MainFunction(void)
{
    /* Stub — no pending events */
}
