/**
 * @file LinTrcv.c
 * @brief LIN Transceiver Driver — External LIN transceiver control
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "LinTrcv.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINTRCV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinTrcv_Init — stub implementation */
Std_ReturnType LinTrcv_Init(const LinTrcv_ConfigType *ConfigPtr)
{
    LINTRCV_Initialized = 1U;
    return E_OK;
}

/** @brief LinTrcv_DeInit — stub implementation */
Std_ReturnType LinTrcv_DeInit(void)
{
    LINTRCV_Initialized = 0U;
    return E_OK;
}

/** @brief LinTrcv_GetVersionInfo — stub implementation */
void LinTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief LinTrcv_SetTrcvMode — stub implementation */
Std_ReturnType LinTrcv_SetTrcvMode(uint8_t TrcvIdx, LinTrcv_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief LinTrcv_GetTrcvMode — stub implementation */
LinTrcv_ModeType LinTrcv_GetTrcvMode(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return LINTRCV_TRCVMODE_NORMAL;
}

/** @brief LinTrcv_WakeUp — stub implementation */
Std_ReturnType LinTrcv_WakeUp(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief LinTrcv_CheckWakeFlag — stub implementation */
LinTrcv_WakeFlagType LinTrcv_CheckWakeFlag(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return LINTRCV_NO_WAKEUP;
}
