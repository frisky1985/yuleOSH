/**
 * @file Com.h
 * @brief AUTOSAR COM — Signal-based I-PDU communication
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef COM_H
#define COM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Com configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Com_ConfigType;


/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Com_Init(void);
extern Std_ReturnType Com_DeInit(void);
extern void Com_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Com_SendSignal(uint16_t SignalId, const uint8_t *SignalDataPtr);
extern Std_ReturnType Com_ReceiveSignal(uint16_t SignalId, uint8_t *SignalDataPtr);
extern void Com_MainFunction(void);
extern void Com_TxConfirmation(PduIdType pduId);
extern void Com_RxIndication(PduIdType pduId);
#ifdef __cplusplus
}
#endif

#endif /* COM_H */
