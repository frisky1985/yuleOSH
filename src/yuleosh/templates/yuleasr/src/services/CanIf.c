/**
 * @file CanIf.c
 * @brief CAN Interface — PDU routing between CAN driver and upper layers
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "CanIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANIF_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanIf_Init — stub implementation */
Std_ReturnType CanIf_Init(void)
{
    AUTOSAR_STUB_UNUSED
    CANIF_SV_Initialized = 1U;
    return E_OK;
}

/** @brief CanIf_DeInit — stub implementation */
Std_ReturnType CanIf_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    CANIF_SV_Initialized = 0U;
    return E_OK;
}

/** @brief CanIf_GetVersionInfo — stub implementation */
void CanIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
