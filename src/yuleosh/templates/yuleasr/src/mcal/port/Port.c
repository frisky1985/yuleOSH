/**
 * @file Port.c
 * @brief Port Driver — Pin mux/direction/pull configuration
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Port.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t PORT_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Port_Init — stub implementation */
Std_ReturnType Port_Init(const Port_ConfigType *ConfigPtr)
{
    PORT_Initialized = 1U;
    return E_OK;
}

/** @brief Port_DeInit — stub implementation */
Std_ReturnType Port_DeInit(void)
{
    PORT_Initialized = 0U;
    return E_OK;
}

/** @brief Port_GetVersionInfo — stub implementation */
void Port_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Port_SetPinDirection — stub implementation */
Std_ReturnType Port_SetPinDirection(Port_PinType Pin, Port_PinDirectionType Direction)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Port_SetPinMode — stub implementation */
Std_ReturnType Port_SetPinMode(Port_PinType Pin, Port_PinModeType Mode)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Port_RefreshPortDirection — stub implementation */
Std_ReturnType Port_RefreshPortDirection(void)
{
    /* Stub — returning default */
    return E_OK;
}
