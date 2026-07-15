/**
 * @file FrIf.h
 * @brief FlexRay Interface — PDU routing between FlexRay driver and upper layers (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef FRIF_SV_H
#define FRIF_SV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief FrIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} FrIf_ConfigType;

typedef uint8_t FrIf_ControllerModeType;
#define FRIF_CS_UNINIT  0x00U
#define FRIF_CS_STARTED 0x01U
#define FRIF_CS_STOPPED 0x02U
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType FrIf_Init(void);
extern Std_ReturnType FrIf_DeInit(void);
extern void FrIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType FrIf_SetControllerMode(uint8_t ControllerId, FrIf_ControllerModeType Mode);
extern Std_ReturnType FrIf_Transmit(PduIdType FrIfTxSduId, const PduInfoType *PduInfoPtr);
extern void FrIf_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* FRIF_SV_H */
