/**
 * @file CanIf.h
 * @brief CAN Interface — PDU routing between CAN driver and upper layers
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full CanIf driver is integrated.
 */

#ifndef CANIF_H
#define CANIF_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanIf_ConfigType;

typedef uint8_t CanIf_ControllerModeType;
#define CANIF_CS_UNINIT  0x00U
#define CANIF_CS_STARTED 0x01U
#define CANIF_CS_STOPPED 0x02U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanIf_Init(void);

extern Std_ReturnType CanIf_DeInit(void);

extern void CanIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanIf_SetControllerMode(uint8_t ControllerId, CanIf_ControllerModeType Mode);

extern CanIf_ControllerModeType CanIf_GetControllerMode(uint8_t ControllerId);

extern Std_ReturnType CanIf_Transmit(PduIdType CanIfTxSduId, const PduInfoType *PduInfoPtr);

extern void CanIf_MainFunction(void);

extern Std_ReturnType CanIf_CancelTransmit(PduIdType CanIfTxSduId);

#ifdef __cplusplus
}
#endif

#endif /* CANIF_H */
