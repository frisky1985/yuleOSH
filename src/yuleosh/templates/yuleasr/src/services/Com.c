/**
 * @file Com.c
 * @brief AUTOSAR COM — Signal-based I-PDU communication
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Com.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t COM_Initialized = 0U;
static uint16_t COM_SignalBuffer[32];

/* ─── API implementations ─────────────────────────── */

/** @brief Com_Init — stub implementation */
Std_ReturnType Com_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    COM_Initialized = 1U;
    return E_OK;
}

/** @brief Com_DeInit — stub implementation */
Std_ReturnType Com_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    COM_Initialized = 0U;
    return E_OK;
}

/** @brief Com_GetVersionInfo — stub implementation */
void Com_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Com_SendSignal — stub implementation */
Std_ReturnType Com_SendSignal(uint16_t SignalId, const uint8_t *SignalDataPtr)
{
    /* AUTOSAR stub — to be implemented */
    (void)SignalId;
    (void)SignalDataPtr;
    return E_OK;
}

/** @brief Com_ReceiveSignal — stub implementation */
Std_ReturnType Com_ReceiveSignal(uint16_t SignalId, uint8_t *SignalDataPtr)
{
    /* AUTOSAR stub — to be implemented */
    (void)SignalId;
    (void)SignalDataPtr;
    return E_OK;
}

/** @brief Com_MainFunction — stub implementation */
void Com_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}

/** @brief Com_TxConfirmation — stub implementation */
void Com_TxConfirmation(PduIdType pduId)
{
    /* AUTOSAR stub — to be implemented */
    (void)pduId;
}

/** @brief Com_RxIndication — stub implementation */
void Com_RxIndication(PduIdType pduId)
{
    /* AUTOSAR stub — to be implemented */
    (void)pduId;
}
