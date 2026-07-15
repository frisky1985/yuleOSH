/**
 * @file MemIf.c
 * @brief Memory Abstraction Interface — NvM abstraction over Fee/Ea
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "MemIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t MEMIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief MemIf_Init — stub implementation */
Std_ReturnType MemIf_Init(void)
{
    MEMIF_Initialized = 1U;
    return E_OK;
}

/** @brief MemIf_DeInit — stub implementation */
Std_ReturnType MemIf_DeInit(void)
{
    MEMIF_Initialized = 0U;
    return E_OK;
}

/** @brief MemIf_GetVersionInfo — stub implementation */
void MemIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief MemIf_Read — stub implementation */
Std_ReturnType MemIf_Read(MemIf_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief MemIf_Write — stub implementation */
Std_ReturnType MemIf_Write(MemIf_BlockIdType BlockId, const uint8_t *DataBufferPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief MemIf_EraseImmediate — stub implementation */
Std_ReturnType MemIf_EraseImmediate(MemIf_BlockIdType BlockId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief MemIf_GetStatus — stub implementation */
MemIf_StatusType MemIf_GetStatus(void)
{
    /* Stub — returning default */
    return MEMIF_IDLE;
}

/** @brief MemIf_MainFunction — stub implementation */
void MemIf_MainFunction(void)
{
    /* Stub — no pending events */
}
