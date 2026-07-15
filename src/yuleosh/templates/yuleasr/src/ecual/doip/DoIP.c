/**
 * @file DoIP.c
 * @brief Diagnostics over IP — ISO 13400-2 Ethernet diagnostics
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "DoIP.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DOIP_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief DoIP_Init — stub implementation */
Std_ReturnType DoIP_Init(void)
{
    DOIP_Initialized = 1U;
    return E_OK;
}

/** @brief DoIP_DeInit — stub implementation */
Std_ReturnType DoIP_DeInit(void)
{
    DOIP_Initialized = 0U;
    return E_OK;
}

/** @brief DoIP_GetVersionInfo — stub implementation */
void DoIP_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief DoIP_OpenSocket — stub implementation */
Std_ReturnType DoIP_OpenSocket(uint16_t Port)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief DoIP_CloseSocket — stub implementation */
Std_ReturnType DoIP_CloseSocket(void)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief DoIP_SendDiagnosticMessage — stub implementation */
Std_ReturnType DoIP_SendDiagnosticMessage(const uint8_t *Payload, uint32_t Length)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief DoIP_MainFunction — stub implementation */
void DoIP_MainFunction(void)
{
    /* Stub — no pending events */
}
