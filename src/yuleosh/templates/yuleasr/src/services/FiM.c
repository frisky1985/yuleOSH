/**
 * @file FiM.c
 * @brief Function Inhibition Manager — Conditional function enable/disable
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "FiM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FIM_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief FiM_Init — stub implementation */
Std_ReturnType FiM_Init(void)
{
    AUTOSAR_STUB_UNUSED
    FIM_SV_Initialized = 1U;
    return E_OK;
}

/** @brief FiM_DeInit — stub implementation */
Std_ReturnType FiM_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    FIM_SV_Initialized = 0U;
    return E_OK;
}

/** @brief FiM_GetVersionInfo — stub implementation */
void FiM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
