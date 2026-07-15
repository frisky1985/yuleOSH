/**
 * @file CanTp.c
 * @brief CAN Transport Layer — ISO 15765-2 multi-frame segmentation
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "CanTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANTP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanTp_Init — stub implementation */
Std_ReturnType CanTp_Init(void)
{
    CANTP_Initialized = 1U;
    return E_OK;
}

/** @brief CanTp_DeInit — stub implementation */
Std_ReturnType CanTp_DeInit(void)
{
    CANTP_Initialized = 0U;
    return E_OK;
}

/** @brief CanTp_GetVersionInfo — stub implementation */
void CanTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief CanTp_Transmit — stub implementation */
Std_ReturnType CanTp_Transmit(PduIdType CanTpTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanTp_CancelTransmit — stub implementation */
Std_ReturnType CanTp_CancelTransmit(PduIdType CanTpTxSduId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanTp_CancelReceive — stub implementation */
Std_ReturnType CanTp_CancelReceive(PduIdType CanTpRxSduId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanTp_MainFunction — stub implementation */
void CanTp_MainFunction(void)
{
    /* Stub — no pending events */
}
