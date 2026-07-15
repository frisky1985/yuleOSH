/**
 * @file FrTp.c
 * @brief FlexRay Transport Layer — ISO 10681-2 segmentation
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "FrTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FRTP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief FrTp_Init — stub implementation */
Std_ReturnType FrTp_Init(void)
{
    FRTP_Initialized = 1U;
    return E_OK;
}

/** @brief FrTp_DeInit — stub implementation */
Std_ReturnType FrTp_DeInit(void)
{
    FRTP_Initialized = 0U;
    return E_OK;
}

/** @brief FrTp_GetVersionInfo — stub implementation */
void FrTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief FrTp_Transmit — stub implementation */
Std_ReturnType FrTp_Transmit(PduIdType FrTpTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief FrTp_MainFunction — stub implementation */
void FrTp_MainFunction(void)
{
    /* Stub — no pending events */
}
