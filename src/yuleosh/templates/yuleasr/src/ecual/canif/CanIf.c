/**
 * @file CanIf.c
 * @brief CAN Interface — PDU routing between CAN driver and upper layers
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "CanIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanIf_Init — stub implementation */
Std_ReturnType CanIf_Init(void)
{
    CANIF_Initialized = 1U;
    return E_OK;
}

/** @brief CanIf_DeInit — stub implementation */
Std_ReturnType CanIf_DeInit(void)
{
    CANIF_Initialized = 0U;
    return E_OK;
}

/** @brief CanIf_GetVersionInfo — stub implementation */
void CanIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief CanIf_SetControllerMode — stub implementation */
Std_ReturnType CanIf_SetControllerMode(uint8_t ControllerId, CanIf_ControllerModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanIf_GetControllerMode — stub implementation */
CanIf_ControllerModeType CanIf_GetControllerMode(uint8_t ControllerId)
{
    /* Stub — returning default */
    return CANIF_CS_UNINIT;
}

/** @brief CanIf_Transmit — stub implementation */
Std_ReturnType CanIf_Transmit(PduIdType CanIfTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanIf_MainFunction — stub implementation */
void CanIf_MainFunction(void)
{
    /* Stub — no pending events */
}

/** @brief CanIf_CancelTransmit — stub implementation */
Std_ReturnType CanIf_CancelTransmit(PduIdType CanIfTxSduId)
{
    /* Stub — returning default */
    return E_OK;
}
