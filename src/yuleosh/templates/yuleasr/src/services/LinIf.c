/**
 * @file LinIf.c
 * @brief LIN Interface — PDU routing between LIN driver and upper layers
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "LinIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINIF_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinIf_Init — stub implementation */
Std_ReturnType LinIf_Init(void)
{
    AUTOSAR_STUB_UNUSED
    LINIF_SV_Initialized = 1U;
    return E_OK;
}

/** @brief LinIf_DeInit — stub implementation */
Std_ReturnType LinIf_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    LINIF_SV_Initialized = 0U;
    return E_OK;
}

/** @brief LinIf_GetVersionInfo — stub implementation */
void LinIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
