/**
 * @file Xcp.c
 * @brief Universal Calibration Protocol — XCP on CAN/Ethernet
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "Xcp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t XCP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Xcp_Init — stub implementation */
Std_ReturnType Xcp_Init(void)
{
    AUTOSAR_STUB_UNUSED
    XCP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief Xcp_DeInit — stub implementation */
Std_ReturnType Xcp_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    XCP_SV_Initialized = 0U;
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
