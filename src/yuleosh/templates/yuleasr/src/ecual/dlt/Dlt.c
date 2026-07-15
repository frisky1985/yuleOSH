/**
 * @file Dlt.c
 * @brief Diagnostic Log and Trace — Runtime logging over CAN/Ethernet
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Dlt.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DLT_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Dlt_Init — stub implementation */
Std_ReturnType Dlt_Init(void)
{
    DLT_Initialized = 1U;
    return E_OK;
}

/** @brief Dlt_DeInit — stub implementation */
Std_ReturnType Dlt_DeInit(void)
{
    DLT_Initialized = 0U;
    return E_OK;
}

/** @brief Dlt_GetVersionInfo — stub implementation */
void Dlt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Dlt_SendLog — stub implementation */
Std_ReturnType Dlt_SendLog(uint8_t LogLevel, const char *AppId, const char *CtxId, const char *Payload)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Dlt_SetLogLevel — stub implementation */
Std_ReturnType Dlt_SetLogLevel(uint8_t LogLevel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Dlt_MainFunction — stub implementation */
void Dlt_MainFunction(void)
{
    /* Stub — no pending events */
}
