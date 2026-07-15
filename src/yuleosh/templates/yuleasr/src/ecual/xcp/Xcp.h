/**
 * @file Xcp.h
 * @brief Universal Calibration Protocol — XCP on CAN/Ethernet
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Xcp driver is integrated.
 */

#ifndef XCP_H
#define XCP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Xcp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Xcp_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Xcp_Init(void);

extern Std_ReturnType Xcp_DeInit(void);

extern void Xcp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern uint8_t Xcp_GetSlaveId(void);

extern Std_ReturnType Xcp_Send(const uint8_t *Data, uint16_t Length);

extern void Xcp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* XCP_H */
