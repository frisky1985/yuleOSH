/**
 * @file IpduM.c
 * @brief I-PDU Multiplexer — Multiplexed PDU routing
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "IpduM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t IPDUM_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief IpduM_Init — stub implementation */
Std_ReturnType IpduM_Init(void)
{
    IPDUM_Initialized = 1U;
    return E_OK;
}

/** @brief IpduM_DeInit — stub implementation */
Std_ReturnType IpduM_DeInit(void)
{
    IPDUM_Initialized = 0U;
    return E_OK;
}

/** @brief IpduM_GetVersionInfo — stub implementation */
void IpduM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief IpduM_Transmit — stub implementation */
Std_ReturnType IpduM_Transmit(PduIdType IpduMTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief IpduM_MainFunction — stub implementation */
void IpduM_MainFunction(void)
{
    /* Stub — no pending events */
}
