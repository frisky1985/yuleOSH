/**
 * @file FrNm.c
 * @brief FlexRay Network Management — NM message handling for FlexRay
 *
 * yuleASR Services stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "FrNm.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t FRNM_Initialized = 0U;
static FrNm_StateType FRNM_State = FRNM_STATE_BUS_SLEEP;

/* ─── API implementations ─────────────────────────── */

/** @brief FrNm_Init — stub implementation */
Std_ReturnType FrNm_Init(void)
{
    /* AUTOSAR stub — to be implemented */
    FRNM_Initialized = 1U;
    FRNM_State = FRNM_STATE_BUS_SLEEP;
    return E_OK;
}

/** @brief FrNm_DeInit — stub implementation */
Std_ReturnType FrNm_DeInit(void)
{
    /* AUTOSAR stub — to be implemented */
    FRNM_Initialized = 0U;
    return E_OK;
}

/** @brief FrNm_GetVersionInfo — stub implementation */
void FrNm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief FrNm_MainFunction — stub implementation */
void FrNm_MainFunction(void)
{
    /* AUTOSAR stub — to be implemented */
}

/** @brief FrNm_GetState — stub implementation */
FrNm_StateType FrNm_GetState(uint8_t nmNodeId)
{
    /* AUTOSAR stub — to be implemented */
    (void)nmNodeId;
    return FRNM_State;
}

/** @brief FrNm_NetworkRequest — stub implementation */
Std_ReturnType FrNm_NetworkRequest(void)
{
    /* AUTOSAR stub — to be implemented */
    FRNM_State = FRNM_STATE_NETWORK;
    return E_OK;
}
