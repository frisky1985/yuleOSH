/**
 * @file Xcp.c
 * @brief Universal Calibration Protocol — XCP on CAN/Ethernet
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Xcp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t XCP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Xcp_Init — stub implementation */
Std_ReturnType Xcp_Init(void)
{
    XCP_Initialized = 1U;
    return E_OK;
}

/** @brief Xcp_DeInit — stub implementation */
Std_ReturnType Xcp_DeInit(void)
{
    XCP_Initialized = 0U;
    return E_OK;
}

/** @brief Xcp_GetVersionInfo — stub implementation */
void Xcp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Xcp_GetSlaveId — stub implementation */
uint8_t Xcp_GetSlaveId(void)
{
    /* Stub — returning default */
    return 0x01;
}

/** @brief Xcp_Send — stub implementation */
Std_ReturnType Xcp_Send(const uint8_t *Data, uint16_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Xcp_MainFunction — stub implementation */
void Xcp_MainFunction(void)
{
    /* Stub — no pending events */
}
