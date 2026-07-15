/**
 * @file SchM.c
 * @brief Schedule Manager — Runnable and task scheduling
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "SchM.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t SCHM_Initialized = 0U;
static uint32_t SCHM_TickCount = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief SchM_Init — stub implementation */
Std_ReturnType SchM_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    SCHM_Initialized = 1U;
    SCHM_TickCount = 0U;
    return E_OK;
}

/** @brief SchM_DeInit — stub implementation */
Std_ReturnType SchM_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    SCHM_Initialized = 0U;
    return E_OK;
}

/** @brief SchM_GetVersionInfo — stub implementation */
void SchM_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief SchM_MainFunction — stub implementation */
void SchM_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
    SCHM_TickCount++;
}
