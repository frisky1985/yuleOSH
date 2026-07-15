/**
 * @file UdsTp.c
 * @brief UDS Transport Protocol — ISO 15765-2 CAN transport layer for UDS
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "UdsTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t UDSTP_Initialized = 0U;
static UdsTp_StateType UDSTP_State = UDSTP_STATE_IDLE;

/* ─── API implementations ─────────────────────────── */

/** @brief UdsTp_Init — stub implementation */
Std_ReturnType UdsTp_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    UDSTP_Initialized = 1U;
    UDSTP_State = UDSTP_STATE_IDLE;
    return E_OK;
}

/** @brief UdsTp_DeInit — stub implementation */
Std_ReturnType UdsTp_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    UDSTP_Initialized = 0U;
    return E_OK;
}

/** @brief UdsTp_GetVersionInfo — stub implementation */
void UdsTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief UdsTp_Transmit — stub implementation */
Std_ReturnType UdsTp_Transmit(const uint8_t *Data, uint16_t Length, UdsTp_ProtocolType Protocol)
{
    /* AUTOSAR stub — to be implemented */
    (void)Data;
    (void)Length;
    (void)Protocol;
    return E_OK;
}

/** @brief UdsTp_CancelTransmit — stub implementation */
Std_ReturnType UdsTp_CancelTransmit(void)
{
    /* AUTOSAR stub — to be implemented */
    return E_OK;
}

/** @brief UdsTp_MainFunction — stub implementation */
void UdsTp_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
