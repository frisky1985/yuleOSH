/**
 * @file RamTst.c
 * @brief RAM Test Driver — March C-/Galpat RAM self-test
 *
 * yuleASR MCAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "RamTst.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t RAMTST_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief RamTst_Init — stub implementation */
Std_ReturnType RamTst_Init(const RamTst_ConfigType *ConfigPtr)
{
    RAMTST_Initialized = 1U;
    return E_OK;
}

/** @brief RamTst_DeInit — stub implementation */
Std_ReturnType RamTst_DeInit(void)
{
    RAMTST_Initialized = 0U;
    return E_OK;
}

/** @brief RamTst_GetVersionInfo — stub implementation */
void RamTst_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief RamTst_StartTest — stub implementation */
Std_ReturnType RamTst_StartTest(RamTst_AreaType Area, RamTst_AlgorithmType Algorithm)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief RamTst_GetResult — stub implementation */
Std_ReturnType RamTst_GetResult(RamTst_AreaType Area, RamTst_TestResultType *ResultPtr)
{
    /* Stub — returning default */
    return E_NOT_OK;
}

/** @brief RamTst_StopTest — stub implementation */
Std_ReturnType RamTst_StopTest(RamTst_AreaType Area)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief RamTst_MainFunction — stub implementation */
void RamTst_MainFunction(void)
{
    /* Stub — no pending events */
}
