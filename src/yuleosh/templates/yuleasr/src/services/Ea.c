/**
 * @file Ea.c
 * @brief EEPROM Abstraction — Unified EEPROM driver interface
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "Ea.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t EA_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Ea_Init — stub implementation */
Std_ReturnType Ea_Init(void)
{
    AUTOSAR_STUB_UNUSED
    EA_SV_Initialized = 1U;
    return E_OK;
}

/** @brief Ea_DeInit — stub implementation */
Std_ReturnType Ea_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    EA_SV_Initialized = 0U;
    return E_OK;
}

/** @brief Ea_GetVersionInfo — stub implementation */
void Ea_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
