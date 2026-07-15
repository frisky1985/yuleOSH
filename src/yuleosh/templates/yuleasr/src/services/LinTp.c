/**
 * @file LinTp.c
 * @brief LIN Transport Protocol — Segmentation and reassembly for LIN
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "LinTp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINTP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinTp_Init — stub implementation */
Std_ReturnType LinTp_Init(void)
{
    AUTOSAR_STUB_UNUSED
    LINTP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief LinTp_DeInit — stub implementation */
Std_ReturnType LinTp_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    LINTP_SV_Initialized = 0U;
    return E_OK;
}

/** @brief LinTp_GetVersionInfo — stub implementation */
void LinTp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
