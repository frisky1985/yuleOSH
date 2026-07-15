/**
 * @file FrTp.c
 * @brief FlexRay Transport Protocol — Segmentation and reassembly for FlexRay
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "FrTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FRTP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief FrTp_Init — stub implementation */
Std_ReturnType FrTp_Init(void)
{
    AUTOSAR_STUB_UNUSED
    FRTP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief FrTp_DeInit — stub implementation */
Std_ReturnType FrTp_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    FRTP_SV_Initialized = 0U;
    return E_OK;
}

/** @brief FrTp_GetVersionInfo — stub implementation */
void FrTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
