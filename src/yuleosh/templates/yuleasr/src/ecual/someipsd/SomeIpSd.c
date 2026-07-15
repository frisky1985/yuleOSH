/**
 * @file SomeIpSd.c
 * @brief SOME/IP Service Discovery — Offer/Find/Subscribe services
 *
 * yuleASR ECUAL stub — skeleton implementation.
 * Replace with full driver implementation from yuleASR.
 */

#include "SomeIpSd.h"

/* ─── Module internal state ──────────────────────── */
static uint8_t SOMEIPSD_Initialized = 0U;

/* ─── API implementations ─────────────────────────── */

/** @brief SomeIpSd_Init — stub implementation */
Std_ReturnType SomeIpSd_Init(void)
{
    SOMEIPSD_Initialized = 1U;
    return E_OK;
}

/** @brief SomeIpSd_DeInit — stub implementation */
Std_ReturnType SomeIpSd_DeInit(void)
{
    SOMEIPSD_Initialized = 0U;
    return E_OK;
}

/** @brief SomeIpSd_GetVersionInfo — stub implementation */
void SomeIpSd_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr)
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

/** @brief SomeIpSd_ServiceOffer — stub implementation */
Std_ReturnType SomeIpSd_ServiceOffer(uint16_t ServiceId, uint16_t InstanceId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief SomeIpSd_ServiceFind — stub implementation */
Std_ReturnType SomeIpSd_ServiceFind(uint16_t ServiceId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief SomeIpSd_ServiceSubscribe — stub implementation */
Std_ReturnType SomeIpSd_ServiceSubscribe(uint16_t ServiceId, uint16_t InstanceId)
{
    /* Stub — returning default */
    return E_OK;
}

/** @brief SomeIpSd_MainFunction — stub implementation */
void SomeIpSd_MainFunction(void)
{
    /* Stub — no pending events */
}
