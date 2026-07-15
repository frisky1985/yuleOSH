/**
 * @file LinIf.c
 * @brief LIN Interface — Schedule table and frame routing
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "LinIf.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t LINIF_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief LinIf_Init — stub implementation */
Std_ReturnType LinIf_Init(void)
{
    LINIF_Initialized = 1U;
    return E_OK;
}

/** @brief LinIf_DeInit — stub implementation */
Std_ReturnType LinIf_DeInit(void)
{
    LINIF_Initialized = 0U;
    return E_OK;
}

/** @brief LinIf_GetVersionInfo — stub implementation */
void LinIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief LinIf_SetSchedule — stub implementation */
Std_ReturnType LinIf_SetSchedule(uint8_t Channel, LinIf_ScheduleType Schedule)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief LinIf_GetSchedule — stub implementation */
LinIf_ScheduleType LinIf_GetSchedule(uint8_t Channel)
{
    /* Stub — returning default */
    return LINIF_SCHEDULE_NONE;
}

/** @brief LinIf_Transmit — stub implementation */
Std_ReturnType LinIf_Transmit(PduIdType LinIfTxSduId, const PduInfoType *PduInfoPtr)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief LinIf_MainFunction — stub implementation */
void LinIf_MainFunction(void)
{
    /* Stub — no pending events */
}
