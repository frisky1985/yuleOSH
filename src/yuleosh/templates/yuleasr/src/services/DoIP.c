/**
 * @file DoIP.c
 * @brief Diagnostics over IP — ISO 13400 diagnostic communication over Ethernet
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "DoIP.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DOIP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief DoIP_Init — stub implementation */
Std_ReturnType DoIP_Init(void)
{
    AUTOSAR_STUB_UNUSED
    DOIP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief DoIP_DeInit — stub implementation */
Std_ReturnType DoIP_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    DOIP_SV_Initialized = 0U;
    return E_OK;
}

/** @brief DoIP_GetVersionInfo — stub implementation */
void DoIP_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
