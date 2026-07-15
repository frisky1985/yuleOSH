/**
 * @file Fee.c
 * @brief Flash EEPROM Emulation — Upper Fee abstraction
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "Fee.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FEE_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Fee_Init — stub implementation */
Std_ReturnType Fee_Init(void)
{
    AUTOSAR_STUB_UNUSED
    FEE_SV_Initialized = 1U;
    return E_OK;
}

/** @brief Fee_DeInit — stub implementation */
Std_ReturnType Fee_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    FEE_SV_Initialized = 0U;
    return E_OK;
}

/** @brief Fee_GetVersionInfo — stub implementation */
void Fee_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
