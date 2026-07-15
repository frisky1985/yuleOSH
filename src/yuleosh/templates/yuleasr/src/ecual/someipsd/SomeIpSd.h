/**
 * @file SomeIpSd.h
 * @brief SOME/IP Service Discovery — Offer/Find/Subscribe services
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full SomeIpSd driver is integrated.
 */

#ifndef SOMEIPSD_H
#define SOMEIPSD_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief SomeIpSd configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} SomeIpSd_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType SomeIpSd_Init(void);

extern Std_ReturnType SomeIpSd_DeInit(void);

extern void SomeIpSd_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType SomeIpSd_ServiceOffer(uint16_t ServiceId, uint16_t InstanceId);

extern Std_ReturnType SomeIpSd_ServiceFind(uint16_t ServiceId);

extern Std_ReturnType SomeIpSd_ServiceSubscribe(uint16_t ServiceId, uint16_t InstanceId);

extern void SomeIpSd_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* SOMEIPSD_H */
