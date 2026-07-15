/**
 * @file EthIf.c
 * @brief Ethernet Interface — PDU routing between Eth driver and upper layers
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "EthIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ETHIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief EthIf_Init — stub implementation */
Std_ReturnType EthIf_Init(void)
{
    ETHIF_Initialized = 1U;
    return E_OK;
}

/** @brief EthIf_DeInit — stub implementation */
Std_ReturnType EthIf_DeInit(void)
{
    ETHIF_Initialized = 0U;
    return E_OK;
}

/** @brief EthIf_GetVersionInfo — stub implementation */
void EthIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief EthIf_SetControllerMode — stub implementation */
Std_ReturnType EthIf_SetControllerMode(uint8_t ControllerId, EthIf_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief EthIf_Transmit — stub implementation */
Std_ReturnType EthIf_Transmit(PduIdType EthIfTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief EthIf_MainFunction — stub implementation */
void EthIf_MainFunction(void)
{
    /* Stub — no pending events */
}
