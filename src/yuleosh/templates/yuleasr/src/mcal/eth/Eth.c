/**
 * @file Eth.c
 * @brief Ethernet Driver — SGMII/RMII 100Mbps/1Gbps
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Eth.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t ETH_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Eth_Init — stub implementation */
Std_ReturnType Eth_Init(const Eth_ConfigType *ConfigPtr)
{
    ETH_Initialized = 1U;
    return E_OK;
}

/** @brief Eth_DeInit — stub implementation */
Std_ReturnType Eth_DeInit(void)
{
    ETH_Initialized = 0U;
    return E_OK;
}

/** @brief Eth_GetVersionInfo — stub implementation */
void Eth_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Eth_Write — stub implementation */
Std_ReturnType Eth_Write(uint32_t Controller, const Eth_FrameType *FramePtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eth_Read — stub implementation */
Std_ReturnType Eth_Read(uint32_t Controller, Eth_FrameType *FramePtr)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief Eth_SetControllerMode — stub implementation */
Std_ReturnType Eth_SetControllerMode(uint32_t Controller, Eth_ModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eth_GetControllerMode — stub implementation */
Eth_ModeType Eth_GetControllerMode(uint32_t Controller)
{
    /* Stub — returning default */
    return ETH_MODE_DOWN;
}

/** @brief Eth_ProvideTxBuffer — stub implementation */
Std_ReturnType Eth_ProvideTxBuffer(uint32_t Controller, Eth_BufIdxType BufIdx, uint8_t **BufferPtr, Eth_FrameType *FramePtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Eth_GetTxErrorCounter — stub implementation */
uint16_t Eth_GetTxErrorCounter(uint32_t Controller)
{
    /* Stub — returning default */
    return 0U;
}
