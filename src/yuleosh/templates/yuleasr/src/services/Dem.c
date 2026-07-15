/**
 * @file Dem.c
 * @brief Diagnostic Event Manager — Event storage and fault memory
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Dem.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DEM_Initialized = 0U;
static Dem_EventStatusType DEM_EventStatus[16];

/* ─── API implementations ─────────────────────────── */

/** @brief Dem_Init — stub implementation */
Std_ReturnType Dem_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    DEM_Initialized = 1U;
    return E_OK;
}

/** @brief Dem_DeInit — stub implementation */
Std_ReturnType Dem_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    DEM_Initialized = 0U;
    return E_OK;
}

/** @brief Dem_GetVersionInfo — stub implementation */
void Dem_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Dem_ReportErrorStatus — stub implementation */
Std_ReturnType Dem_ReportErrorStatus(Dem_EventIdType EventId, Dem_EventStatusType EventStatus)
{
    /* AUTOSAR stub — to be implemented */
    if (EventId < 16U)
    {
        DEM_EventStatus[EventId] = EventStatus;
    }
    return E_OK;
}

/** @brief Dem_GetEventStatus — stub implementation */
Dem_EventStatusType Dem_GetEventStatus(Dem_EventIdType EventId)
{
    /* AUTOSAR stub — to be implemented */
    if (EventId < 16U)
    {
        return DEM_EventStatus[EventId];
    }
    return DEM_EVENT_STATUS_PASSED;
}

/** @brief Dem_MainFunction — stub implementation */
void Dem_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
