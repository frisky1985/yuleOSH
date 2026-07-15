/**
 * @file WdgIf.c
 * @brief Watchdog Interface — Abstraction layer for hardware watchdog drivers
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "WdgIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t WDGIF_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief WdgIf_Init — stub implementation */
Std_ReturnType WdgIf_Init(void)
{
    AUTOSAR_STUB_UNUSED
    WDGIF_SV_Initialized = 1U;
    return E_OK;
}

/** @brief WdgIf_DeInit — stub implementation */
Std_ReturnType WdgIf_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    WDGIF_SV_Initialized = 0U;
    return E_OK;
}

/** @brief WdgIf_GetVersionInfo — stub implementation */
void WdgIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
