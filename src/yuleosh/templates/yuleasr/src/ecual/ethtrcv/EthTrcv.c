/**
 * @file EthTrcv.c
 * @brief Ethernet Transceiver Driver — External PHY control
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "EthTrcv.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ETHTRCV_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief EthTrcv_Init — stub implementation */
Std_ReturnType EthTrcv_Init(const EthTrcv_ConfigType *ConfigPtr)
{
    ETHTRCV_Initialized = 1U;
    return E_OK;
}

/** @brief EthTrcv_DeInit — stub implementation */
Std_ReturnType EthTrcv_DeInit(void)
{
    ETHTRCV_Initialized = 0U;
    return E_OK;
}

/** @brief EthTrcv_GetVersionInfo — stub implementation */
void EthTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief EthTrcv_SetTrcvMode — stub implementation */
Std_ReturnType EthTrcv_SetTrcvMode(uint8_t TrcvIdx, EthTrcv_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief EthTrcv_GetTrcvMode — stub implementation */
EthTrcv_ModeType EthTrcv_GetTrcvMode(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return ETHTRCV_MODE_NORMAL;
}

/** @brief EthTrcv_CheckWakeFlag — stub implementation */
EthTrcv_WakeFlagType EthTrcv_CheckWakeFlag(uint8_t TrcvIdx)
{
    /* Stub — returning default */
    return ETHTRCV_NO_WAKEUP;
}
