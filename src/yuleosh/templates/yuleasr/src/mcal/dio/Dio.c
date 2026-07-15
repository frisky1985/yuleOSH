/**
 * @file Dio.c
 * @brief DIO Driver — Digital I/O channel/port level access
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Dio.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DIO_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Dio_Init — stub implementation */
Std_ReturnType Dio_Init(const Dio_ConfigType *ConfigPtr)
{
    DIO_Initialized = 1U;
    return E_OK;
}

/** @brief Dio_DeInit — stub implementation */
Std_ReturnType Dio_DeInit(void)
{
    DIO_Initialized = 0U;
    return E_OK;
}

/** @brief Dio_GetVersionInfo — stub implementation */
void Dio_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Dio_ReadChannel — stub implementation */
Dio_LevelType Dio_ReadChannel(Dio_ChannelType ChannelId)
{
    /* Stub — returning default */
    return STD_LOW;
}

/** @brief Dio_WriteChannel — stub implementation */
Std_ReturnType Dio_WriteChannel(Dio_ChannelType ChannelId, Dio_LevelType Level)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Dio_ReadPort — stub implementation */
Dio_PortLevelType Dio_ReadPort(Dio_PortType PortId)
{
    /* Stub — returning default */
    return 0U;
}

/** @brief Dio_WritePort — stub implementation */
Std_ReturnType Dio_WritePort(Dio_PortType PortId, Dio_PortLevelType Level)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Dio_FlipChannel — stub implementation */
Dio_LevelType Dio_FlipChannel(Dio_ChannelType ChannelId)
{
    /* Stub — returning default */
    return STD_LOW;
}
