/**
 * @file Ea.c
 * @brief EEPROM Abstraction — NvM backing over external EEPROM
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Ea.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t EA_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Ea_Init — stub implementation */
Std_ReturnType Ea_Init(void)
{
    EA_Initialized = 1U;
    return E_OK;
}

/** @brief Ea_DeInit — stub implementation */
Std_ReturnType Ea_DeInit(void)
{
    EA_Initialized = 0U;
    return E_OK;
}

/** @brief Ea_GetVersionInfo — stub implementation */
void Ea_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Ea_Read — stub implementation */
Std_ReturnType Ea_Read(Ea_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Ea_Write — stub implementation */
Std_ReturnType Ea_Write(Ea_BlockIdType BlockId, const uint8_t *DataBufferPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Ea_GetStatus — stub implementation */
Ea_StatusType Ea_GetStatus(void)
{
    /* Stub — returning default */
    return EA_IDLE;
}

/** @brief Ea_MainFunction — stub implementation */
void Ea_MainFunction(void)
{
    /* Stub — no pending events */
}
