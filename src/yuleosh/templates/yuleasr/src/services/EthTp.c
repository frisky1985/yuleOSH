/**
 * @file EthTp.c
 * @brief Ethernet Transport Protocol — Segmentation and reassembly for Ethernet frames
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "EthTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ETHTP_Initialized = 0U;
static EthTp_StateType ETHTP_State = ETHTP_STATE_IDLE;

/* ─── API implementations ─────────────────────────── */

/** @brief EthTp_Init — stub implementation */
Std_ReturnType EthTp_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    ETHTP_Initialized = 1U;
    return E_OK;
}

/** @brief EthTp_DeInit — stub implementation */
Std_ReturnType EthTp_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    ETHTP_Initialized = 0U;
    return E_OK;
}

/** @brief EthTp_GetVersionInfo — stub implementation */
void EthTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief EthTp_Transmit — stub implementation */
Std_ReturnType EthTp_Transmit(PduIdType EthTpTxSduId, const PduInfoType *PduInfoPtr)
{
    /* AUTOSAR stub — to be implemented */
    (void)EthTpTxSduId;
    (void)PduInfoPtr;
    return E_OK;
}

/** @brief EthTp_CancelTransmit — stub implementation */
Std_ReturnType EthTp_CancelTransmit(PduIdType EthTpTxSduId)
{
    /* AUTOSAR stub — to be implemented */
    (void)EthTpTxSduId;
    return E_OK;
}

/** @brief EthTp_MainFunction — stub implementation */
void EthTp_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}

/** @brief EthTp_RxIndication — stub implementation */
void EthTp_RxIndication(PduIdType pduId)
{
    /* AUTOSAR stub — to be implemented */
    (void)pduId;
}

/** @brief EthTp_TxConfirmation — stub implementation */
void EthTp_TxConfirmation(PduIdType pduId)
{
    /* AUTOSAR stub — to be implemented */
    (void)pduId;
}
