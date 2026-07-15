/**
 * @file J1939Tp.h
 * @brief J1939 Transport Protocol — J1939 BAM/CMDT message segmentation (reference: services layer)
 *
 * yuleASR Services stub — skeleton for build integration. *
 * NOTE: ECUAL-level counterpart exists in yuleASR.
 * This Services-layer stub references the ECUAL API.
 */

#ifndef J1939TP_SV_H
#define J1939TP_SV_H

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

typedef uint8_t J1939Tp_StateType;
#define J1939TP_STATE_IDLE  0x00U
#define J1939TP_STATE_TX    0x01U
#define J1939TP_STATE_RX    0x02U

typedef uint16_t J1939Tp_PGNType;
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

#endif /* J1939TP_SV_H */
