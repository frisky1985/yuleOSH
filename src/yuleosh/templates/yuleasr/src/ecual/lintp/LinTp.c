/**
 * @file LinTp.c
 * @brief LIN Transport Layer — LIN diagnostic transport
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "LinTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINTP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinTp_Init — stub implementation */
Std_ReturnType LinTp_Init(void)
{
    LINTP_Initialized = 1U;
    return E_OK;
}

/** @brief LinTp_DeInit — stub implementation */
Std_ReturnType LinTp_DeInit(void)
{
    LINTP_Initialized = 0U;
    return E_OK;
}

/** @brief LinTp_GetVersionInfo — stub implementation */
void LinTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief LinTp_Transmit — stub implementation */
Std_ReturnType LinTp_Transmit(PduIdType LinTpTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief LinTp_MainFunction — stub implementation */
void LinTp_MainFunction(void)
{
    /* Stub — no pending events */
}
