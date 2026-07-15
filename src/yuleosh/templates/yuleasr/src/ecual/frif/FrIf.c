/**
 * @file FrIf.c
 * @brief FlexRay Interface — FlexRay communication channel abstraction
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "FrIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FRIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief FrIf_Init — stub implementation */
Std_ReturnType FrIf_Init(void)
{
    FRIF_Initialized = 1U;
    return E_OK;
}

/** @brief FrIf_DeInit — stub implementation */
Std_ReturnType FrIf_DeInit(void)
{
    FRIF_Initialized = 0U;
    return E_OK;
}

/** @brief FrIf_GetVersionInfo — stub implementation */
void FrIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief FrIf_Transmit — stub implementation */
Std_ReturnType FrIf_Transmit(PduIdType FrIfTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief FrIf_MainFunction — stub implementation */
void FrIf_MainFunction(void)
{
    /* Stub — no pending events */
}
