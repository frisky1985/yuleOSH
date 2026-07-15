/**
 * @file EthSm.c
 * @brief Ethernet State Manager — Controller state arbitration for ETH
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "EthSm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ETHSM_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief EthSm_Init — stub implementation */
Std_ReturnType EthSm_Init(void)
{
    ETHSM_Initialized = 1U;
    return E_OK;
}

/** @brief EthSm_DeInit — stub implementation */
Std_ReturnType EthSm_DeInit(void)
{
    ETHSM_Initialized = 0U;
    return E_OK;
}

/** @brief EthSm_GetVersionInfo — stub implementation */
void EthSm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief EthSm_RequestComMode — stub implementation */
Std_ReturnType EthSm_RequestComMode(uint8_t Network, EthSm_ComModeType ComMode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief EthSm_MainFunction — stub implementation */
void EthSm_MainFunction(void)
{
    /* Stub — no pending events */
}
