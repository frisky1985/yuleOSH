/**
 * @file IpHwAb.h
 * @brief I/O Hardware Abstraction — Unified IO signal interface
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full IpHwAb driver is integrated.
 */

#ifndef IPHWAB_H
#define IPHWAB_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief IpHwAb configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} IpHwAb_ConfigType;

typedef uint16_t IpHwAb_SignalIdType;

typedef uint32_t IpHwAb_SignalValueType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType IpHwAb_Init(void);

extern Std_ReturnType IpHwAb_DeInit(void);

extern void IpHwAb_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType IpHwAb_ReadSignal(IpHwAb_SignalIdType SignalId, IpHwAb_SignalValueType *ValuePtr);

extern Std_ReturnType IpHwAb_WriteSignal(IpHwAb_SignalIdType SignalId, IpHwAb_SignalValueType Value);

extern void IpHwAb_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* IPHWAB_H */
