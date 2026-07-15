/**
 * @file DoIP.h
 * @brief Diagnostics over IP — ISO 13400-2 Ethernet diagnostics
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full DoIP driver is integrated.
 */

#ifndef DOIP_H
#define DOIP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief DoIP configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} DoIP_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType DoIP_Init(void);

extern Std_ReturnType DoIP_DeInit(void);

extern void DoIP_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType DoIP_OpenSocket(uint16_t Port);

extern Std_ReturnType DoIP_CloseSocket(void);

extern Std_ReturnType DoIP_SendDiagnosticMessage(const uint8_t *Payload, uint32_t Length);

extern void DoIP_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* DOIP_H */
