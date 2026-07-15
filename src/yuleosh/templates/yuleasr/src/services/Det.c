/**
 * @file Det.c
 * @brief Default Error Tracer — Development error logging and reporting
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "Det.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t DET_Initialized = 0U;
static uint8_t DET_LastErrorInfo[4]; /* ModuleId, InstanceId, ApiId, ErrorId */

/* ─── API implementations ─────────────────────────── */

/** @brief Det_Init — stub implementation */
Std_ReturnType Det_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    DET_Initialized = 1U;
    return E_OK;
}

/** @brief Det_DeInit — stub implementation */
Std_ReturnType Det_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    DET_Initialized = 0U;
    return E_OK;
}

/** @brief Det_GetVersionInfo — stub implementation */
void Det_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief Det_ReportError — stub implementation */
void Det_ReportError(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId)
{
    /* AUTOSAR stub — to be implemented */
    DET_LastErrorInfo[0] = (uint8_t)(ModuleId >> 8U);
    DET_LastErrorInfo[1] = (uint8_t)(ModuleId & 0xFFU);
    DET_LastErrorInfo[2] = InstanceId;
    DET_LastErrorInfo[3] = ApiId;
    (void)ErrorId;
}

/** @brief Det_ReportRuntimeError — stub implementation */
void Det_ReportRuntimeError(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId)
{
    /* AUTOSAR stub — to be implemented */
    Det_ReportError(ModuleId, InstanceId, ApiId, ErrorId);
}

/** @brief Det_ReportTransientFault — stub implementation */
void Det_ReportTransientFault(uint16_t ModuleId, uint8_t InstanceId, uint8_t ApiId, uint8_t ErrorId)
{
    /* AUTOSAR stub — to be implemented */
    Det_ReportError(ModuleId, InstanceId, ApiId, ErrorId);
}

/** @brief Det_MainFunction — stub implementation */
void Det_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}
