/**
 * @file CanTp.c
 * @brief CAN Transport Protocol — Segmentation and reassembly for CAN
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "CanTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANTP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanTp_Init — stub implementation */
Std_ReturnType CanTp_Init(void)
{
    AUTOSAR_STUB_UNUSED
    CANTP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief CanTp_DeInit — stub implementation */
Std_ReturnType CanTp_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    CANTP_SV_Initialized = 0U;
    return E_OK;
}

/** @brief CanTp_GetVersionInfo — stub implementation */
void CanTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
