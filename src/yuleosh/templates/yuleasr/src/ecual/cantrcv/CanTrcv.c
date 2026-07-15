/**
 * @file CanTrcv.c
 * @brief CAN Transceiver Driver — External CAN transceiver control
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "CanTrcv.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CANTRCV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief CanTrcv_Init — stub implementation */
Std_ReturnType CanTrcv_Init(const CanTrcv_ConfigType *ConfigPtr)
{
    CANTRCV_Initialized = 1U;
    return E_OK;
}

/** @brief CanTrcv_DeInit — stub implementation */
Std_ReturnType CanTrcv_DeInit(void)
{
    CANTRCV_Initialized = 0U;
    return E_OK;
}

/** @brief CanTrcv_GetVersionInfo — stub implementation */
void CanTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief CanTrcv_SetTrcvMode — stub implementation */
Std_ReturnType CanTrcv_SetTrcvMode(uint8_t TrcvIdx, CanTrcv_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanTrcv_GetTrcvMode — stub implementation */
CanTrcv_ModeType CanTrcv_GetTrcvMode(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return CANTRCV_TRCVMODE_NORMAL;
}

/** @brief CanTrcv_WakeUp — stub implementation */
Std_ReturnType CanTrcv_WakeUp(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief CanTrcv_CheckWakeFlag — stub implementation */
CanTrcv_WakeFlagType CanTrcv_CheckWakeFlag(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return CANTRCV_NO_WAKEUP;
}

/** @brief CanTrcv_ClearWakeFlag — stub implementation */
Std_ReturnType CanTrcv_ClearWakeFlag(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return E_OK;
}
