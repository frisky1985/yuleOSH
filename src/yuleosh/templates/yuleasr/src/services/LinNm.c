/**
 * @file LinNm.c
 * @brief LIN Network Management — NM message handling for LIN
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "LinNm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINNM_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinNm_Init — stub implementation */
Std_ReturnType LinNm_Init(void)
{
    AUTOSAR_STUB_UNUSED
    LINNM_SV_Initialized = 1U;
    return E_OK;
}

/** @brief LinNm_DeInit — stub implementation */
Std_ReturnType LinNm_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    LINNM_SV_Initialized = 0U;
    return E_OK;
}

/** @brief LinNm_GetVersionInfo — stub implementation */
void LinNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
