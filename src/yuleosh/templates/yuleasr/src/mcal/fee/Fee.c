/**
 * @file Fee.c
 * @brief Flash EEPROM Emulation (MCAL-level) — Wear-leveling over flash
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Fee.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FEE_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Fee_Init — stub implementation */
Std_ReturnType Fee_Init(const Fee_ConfigType *ConfigPtr)
{
    FEE_Initialized = 1U;
    return E_OK;
}

/** @brief Fee_DeInit — stub implementation */
Std_ReturnType Fee_DeInit(void)
{
    FEE_Initialized = 0U;
    return E_OK;
}

/** @brief Fee_GetVersionInfo — stub implementation */
void Fee_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Fee_Read — stub implementation */
Std_ReturnType Fee_Read(Fee_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fee_Write — stub implementation */
Std_ReturnType Fee_Write(Fee_BlockIdType BlockId, const uint8_t *DataBufferPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fee_EraseImmediate — stub implementation */
Std_ReturnType Fee_EraseImmediate(Fee_BlockIdType BlockId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Fee_GetStatus — stub implementation */
Fee_StatusType Fee_GetStatus(void)
{
    /* Stub — returning default */
    return FEE_IDLE;
}

/** @brief Fee_MainFunction — stub implementation */
void Fee_MainFunction(void)
{
    /* Stub — no pending events */
}

/** @brief Fee_Cancel — stub implementation */
Std_ReturnType Fee_Cancel(void)
{
    /* Stub — returning default */
    return E_OK;
}
