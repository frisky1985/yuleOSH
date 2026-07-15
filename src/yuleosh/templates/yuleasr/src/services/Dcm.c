/**
 * @file Dcm.c
 * @brief Diagnostic Communication Manager — UDS request routing & processing
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Dcm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DCM_Initialized = 0U;
static Dcm_SessionType DCM_CurrentSession = DCM_DEFAULT_SESSION;

/* ─── API implementations ─────────────────────────── */

/** @brief Dcm_Init — stub implementation */
Std_ReturnType Dcm_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    DCM_Initialized = 1U;
    DCM_CurrentSession = DCM_DEFAULT_SESSION;
    return E_OK;
}

/** @brief Dcm_DeInit — stub implementation */
Std_ReturnType Dcm_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    DCM_Initialized = 0U;
    return E_OK;
}

/** @brief Dcm_GetVersionInfo — stub implementation */
void Dcm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Dcm_MainFunction — stub implementation */
void Dcm_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}

/** @brief Dcm_RequestProcess — stub implementation */
Std_ReturnType Dcm_RequestProcess(Dcm_OpStatusType opStatus)
{
    /* AUTOSAR stub — to be implemented */
    (void)opStatus;
    return E_OK;
}

/** @brief Dcm_SetSession — stub implementation */
Std_ReturnType Dcm_SetSession(Dcm_SessionType Session)
{
    /* AUTOSAR stub — to be implemented */
    DCM_CurrentSession = Session;
    return E_OK;
}

/** @brief Dcm_GetSession — stub implementation */
Dcm_SessionType Dcm_GetSession(void)
{
    /* AUTOSAR stub — to be implemented */
    return DCM_CurrentSession;
}
