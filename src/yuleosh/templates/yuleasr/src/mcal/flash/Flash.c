/**
 * @file Flash.c
 * @brief Flash Low-Level Driver — Sector/program/read operations
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Flash.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FLASH_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Flash_Init — stub implementation */
Std_ReturnType Flash_Init(const Flash_ConfigType *ConfigPtr)
{
    FLASH_Initialized = 1U;
    return E_OK;
}

/** @brief Flash_DeInit — stub implementation */
Std_ReturnType Flash_DeInit(void)
{
    FLASH_Initialized = 0U;
    return E_OK;
}

/** @brief Flash_GetVersionInfo — stub implementation */
void Flash_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Flash_EraseSector — stub implementation */
Std_ReturnType Flash_EraseSector(Flash_SectorType Sector)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Flash_ProgramWord — stub implementation */
Std_ReturnType Flash_ProgramWord(Flash_AddressType Address, uint32_t Data)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Flash_ProgramPage — stub implementation */
Std_ReturnType Flash_ProgramPage(Flash_AddressType Address, const uint32_t *DataPtr, uint32_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Flash_Read — stub implementation */
Std_ReturnType Flash_Read(Flash_AddressType Address, uint32_t *DataPtr, uint32_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Flash_GetStatus — stub implementation */
Flash_StatusType Flash_GetStatus(void)
{
    /* Stub — returning default */
    return FLASH_IDLE;
}

/** @brief Flash_GetResult — stub implementation */
Flash_ResultType Flash_GetResult(void)
{
    /* Stub — returning default */
    return FLASH_RESULT_OK;
}
