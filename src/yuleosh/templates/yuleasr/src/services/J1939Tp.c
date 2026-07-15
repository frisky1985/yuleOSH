/**
 * @file J1939Tp.c
 * @brief J1939 Transport Protocol — J1939 BAM/CMDT message segmentation
 *
 * yuleASR Services stub — skeleton implementation.
 *
 * NOTE: Full implementation lives in the ECUAL layer.
 * This Services-layer file provides a forwarding stub
 * until the ECUAL module is fully integrated.
 */

#include "J1939Tp.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t J1939TP_SV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief J1939Tp_Init — stub implementation */
Std_ReturnType J1939Tp_Init(void)
{
    AUTOSAR_STUB_UNUSED
    J1939TP_SV_Initialized = 1U;
    return E_OK;
}

/** @brief J1939Tp_DeInit — stub implementation */
Std_ReturnType J1939Tp_DeInit(void)
{
    AUTOSAR_STUB_UNUSED
    J1939TP_SV_Initialized = 0U;
    return E_OK;
}

/** @brief J1939Tp_GetVersionInfo — stub implementation */
void J1939Tp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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
