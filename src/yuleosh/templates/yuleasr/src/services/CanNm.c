/**
 * @file CanNm.c
 * @brief CAN Network Management — NM message handling for CAN
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "CanNm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANNM_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanNm_Init — stub implementation */
Std_ReturnType CanNm_Init(void)
{
    AUTOSAR_STUB_UNUSED
    CANNM_SV_Initialized = 1U;
    return E_OK;
}

/** @brief CanNm_DeInit — stub implementation */
Std_ReturnType CanNm_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    CANNM_SV_Initialized = 0U;
    return E_OK;
}

/** @brief CanNm_GetVersionInfo — stub implementation */
void CanNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
