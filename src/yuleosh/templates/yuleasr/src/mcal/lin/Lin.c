/**
 * @file Lin.c
 * @brief LIN Driver — LIN 2.2 master/slave
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Lin.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LIN_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief Lin_Init — stub implementation */
Std_ReturnType Lin_Init(const Lin_ConfigType *ConfigPtr)
{
    LIN_Initialized = 1U;
    return E_OK;
}

/** @brief Lin_DeInit — stub implementation */
Std_ReturnType Lin_DeInit(void)
{
    LIN_Initialized = 0U;
    return E_OK;
}

/** @brief Lin_GetVersionInfo — stub implementation */
void Lin_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Lin_SendFrame — stub implementation */
Std_ReturnType Lin_SendFrame(const Lin_PduType *PduPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Lin_ReceiveFrame — stub implementation */
Std_ReturnType Lin_ReceiveFrame(Lin_PduType *PduPtr)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief Lin_GoToSleep — stub implementation */
Std_ReturnType Lin_GoToSleep(Lin_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Lin_GoToSleepInternal — stub implementation */
Std_ReturnType Lin_GoToSleepInternal(Lin_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief Lin_WakeUp — stub implementation */
Std_ReturnType Lin_WakeUp(Lin_ChannelType Channel)
{
    /* Stub — returning default */
    return E_OK;
}
