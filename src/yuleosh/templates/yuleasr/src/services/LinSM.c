/**
 * @file LinSM.c
 * @brief LIN State Manager — LIN controller and transceiver state management
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "LinSM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINSM_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinSM_Init — stub implementation */
Std_ReturnType LinSM_Init(void)
{
    AUTOSAR_STUB_UNUSED
    LINSM_SV_Initialized = 1U;
    return E_OK;
}

/** @brief LinSM_DeInit — stub implementation */
Std_ReturnType LinSM_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    LINSM_SV_Initialized = 0U;
    return E_OK;
}

/** @brief LinSM_GetVersionInfo — stub implementation */
void LinSM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
