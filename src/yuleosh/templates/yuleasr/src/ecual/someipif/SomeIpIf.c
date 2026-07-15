/**
 * @file SomeIpIf.c
 * @brief SOME/IP Interface — SOME/IP PDU routing between SoAd and Eth
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "SomeIpIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t SOMEIPIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief SomeIpIf_Init — stub implementation */
Std_ReturnType SomeIpIf_Init(void)
{
    SOMEIPIF_Initialized = 1U;
    return E_OK;
}

/** @brief SomeIpIf_DeInit — stub implementation */
Std_ReturnType SomeIpIf_DeInit(void)
{
    SOMEIPIF_Initialized = 0U;
    return E_OK;
}

/** @brief SomeIpIf_GetVersionInfo — stub implementation */
void SomeIpIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief SomeIpIf_Transmit — stub implementation */
Std_ReturnType SomeIpIf_Transmit(PduIdType SomeIpIfTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief SomeIpIf_MainFunction — stub implementation */
void SomeIpIf_MainFunction(void)
{
    /* Stub — no pending events */
}
