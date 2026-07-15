/**
 * @file CanNm.c
 * @brief CAN Network Management — NM PDU coordination
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "CanNm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANNM_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanNm_Init — stub implementation */
Std_ReturnType CanNm_Init(void)
{
    CANNM_Initialized = 1U;
    return E_OK;
}

/** @brief CanNm_DeInit — stub implementation */
Std_ReturnType CanNm_DeInit(void)
{
    CANNM_Initialized = 0U;
    return E_OK;
}

/** @brief CanNm_GetVersionInfo — stub implementation */
void CanNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief CanNm_Transmit — stub implementation */
Std_ReturnType CanNm_Transmit(PduIdType CanNmTxPduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanNm_NetworkRequest — stub implementation */
Std_ReturnType CanNm_NetworkRequest(uint8_t CanNmChannel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanNm_NetworkRelease — stub implementation */
Std_ReturnType CanNm_NetworkRelease(uint8_t CanNmChannel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanNm_MainFunction — stub implementation */
void CanNm_MainFunction(void)
{
    /* Stub — no pending events */
}
