/**
 * @file Dlt.c
 * @brief Diagnostic Log and Trace — Runtime logging over CAN/Ethernet
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "Dlt.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DLT_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Dlt_Init — stub implementation */
Std_ReturnType Dlt_Init(void)
{
    AUTOSAR_STUB_UNUSED
    DLT_SV_Initialized = 1U;
    return E_OK;
}

/** @brief Dlt_DeInit — stub implementation */
Std_ReturnType Dlt_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    DLT_SV_Initialized = 0U;
    return E_OK;
}

/** @brief Dlt_GetVersionInfo — stub implementation */
void Dlt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
