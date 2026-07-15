/**
 * @file Srp.c
 * @brief Synchronous Real-time Protocol — Time-synchronized data exchange
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Srp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t SRP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Srp_Init — stub implementation */
Std_ReturnType Srp_Init(void)
{
    SRP_Initialized = 1U;
    return E_OK;
}

/** @brief Srp_DeInit — stub implementation */
Std_ReturnType Srp_DeInit(void)
{
    SRP_Initialized = 0U;
    return E_OK;
}

/** @brief Srp_GetVersionInfo — stub implementation */
void Srp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Srp_Transmit — stub implementation */
Std_ReturnType Srp_Transmit(PduIdType SrpTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Srp_MainFunction — stub implementation */
void Srp_MainFunction(void)
{
    /* Stub — no pending events */
}
