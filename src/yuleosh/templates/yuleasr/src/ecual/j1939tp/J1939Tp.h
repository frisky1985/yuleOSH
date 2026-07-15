/**
 * @file J1939Tp.h
 * @brief J1939 Transport Layer — Multi-packet BAM/CMDT messaging
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full J1939Tp driver is integrated.
 */

#ifndef J1939TP_H
#define J1939TP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief J1939Tp configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} J1939Tp_ConfigType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType J1939Tp_Init(void);

extern Std_ReturnType J1939Tp_DeInit(void);

extern void J1939Tp_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType J1939Tp_Transmit(PduIdType J1939TpTxSduId, const PduInfoType *PduInfoPtr);

extern Std_ReturnType J1939Tp_CancelTransmit(PduIdType J1939TpTxSduId);

extern void J1939Tp_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* J1939TP_H */
