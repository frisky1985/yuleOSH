/**
 * @file DoIP.h
 * @brief Diagnostics over IP — ISO 13400 diagnostic communication over Ethernet (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef DOIP_SV_H
#define DOIP_SV_H

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

typedef uint8_t DoIP_StateType;
#define DOIP_STATE_IDLE           0x00U
#define DOIP_STATE_INITIALIZED    0x01U
#define DOIP_STATE_ACTIVE         0x02U

typedef uint8_t DoIP_NodeType;
#define DOIP_NODE_GATEWAY  0x01U
#define DOIP_NODE_NODE     0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType DoIP_Init(void);
extern Std_ReturnType DoIP_DeInit(void);
extern void DoIP_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType DoIP_Start(const uint8_t *ConfigPtr);
extern Std_ReturnType DoIP_Stop(void);
extern void DoIP_MainFunction(void);
extern Std_ReturnType DoIP_SendDiagnostic(uint16_t TargetAddr, const uint8_t *Data, uint16_t Length);
#ifdef __cplusplus
}
#endif

#endif /* DOIP_SV_H */
