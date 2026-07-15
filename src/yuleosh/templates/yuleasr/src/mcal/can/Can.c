/**
 * @file Can.c
 * @brief CAN Driver — CAN 2.0 / CAN FD controller
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Can.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t CAN_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Can_Init — stub implementation */
Std_ReturnType Can_Init(const Can_ConfigType *ConfigPtr)
{
    CAN_Initialized = 1U;
    return E_OK;
}

/** @brief Can_DeInit — stub implementation */
Std_ReturnType Can_DeInit(void)
{
    CAN_Initialized = 0U;
    return E_OK;
}

/** @brief Can_GetVersionInfo — stub implementation */
void Can_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Can_SetBaudrate — stub implementation */
Std_ReturnType Can_SetBaudrate(Can_ControllerType Controller, uint16_t Baudrate)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Can_Write — stub implementation */
Std_ReturnType Can_Write(Can_HwHandleType Mailbox, const Can_PduType *PduInfo)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Can_Read — stub implementation */
Std_ReturnType Can_Read(Can_HwHandleType Mailbox, Can_PduType *PduInfo)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief Can_MainFunction_Read — stub implementation */
void Can_MainFunction_Read(void)
{
    /* Stub — no pending events */
}

/** @brief Can_MainFunction_Write — stub implementation */
void Can_MainFunction_Write(void)
{
    /* Stub — no pending events */
}
