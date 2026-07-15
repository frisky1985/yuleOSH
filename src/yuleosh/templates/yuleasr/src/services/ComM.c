/**
 * @file ComM.c
 * @brief Communication Manager — Channel and bus state coordination
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "ComM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t COMM_Initialized = 0U;
static ComM_StateType COMM_CurrentMode = COMM_NO_COMMUNICATION;

/* ─── API implementations ─────────────────────────── */

/** @brief ComM_Init — stub implementation */
Std_ReturnType ComM_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    COMM_Initialized = 1U;
    COMM_CurrentMode = COMM_NO_COMMUNICATION;
    return E_OK;
}

/** @brief ComM_DeInit — stub implementation */
Std_ReturnType ComM_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    COMM_Initialized = 0U;
    return E_OK;
}

/** @brief ComM_GetVersionInfo — stub implementation */
void ComM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief ComM_RequestComMode — stub implementation */
Std_ReturnType ComM_RequestComMode(ComM_UserHandleType User, ComM_StateType RequestedMode)
{
    /* AUTOSAR stub — to be implemented */
    (void)User;
    COMM_CurrentMode = RequestedMode;
    return E_OK;
}

/** @brief ComM_GetCurrentComMode — stub implementation */
ComM_StateType ComM_GetCurrentComMode(uint8_t ChannelId)
{
    /* AUTOSAR stub — to be implemented */
    (void)ChannelId;
    return COMM_CurrentMode;
}

/** @brief ComM_MainFunction — stub implementation */
void ComM_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
