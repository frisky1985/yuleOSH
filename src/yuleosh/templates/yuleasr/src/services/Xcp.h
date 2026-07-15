/**
 * @file Xcp.h
 * @brief Universal Calibration Protocol — XCP on CAN/Ethernet (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef XCP_SV_H
#define XCP_SV_H

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

#endif /* XCP_SV_H */
