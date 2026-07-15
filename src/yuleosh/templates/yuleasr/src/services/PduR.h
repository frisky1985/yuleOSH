/**
 * @file PduR.h
 * @brief PDU Router — PDU routing between modules and communication bus
 *
 * yuleASR Services stub — skeleton for build integration.
 */

#ifndef PDUR_H
#define PDUR_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief PduR configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} PduR_ConfigType;

typedef uint8_t PduR_StateType;
#define PDUR_STATE_UNINIT   0x00U
#define PDUR_STATE_ONLINE   0x01U
#define PDUR_STATE_OFFLINE  0x02U

typedef uint8_t PduR_RouteType;
#define PDUR_ROUTE_STATIC   0x00U
#define PDUR_ROUTE_DYNAMIC  0x01U

typedef uint8_t PduR_PduIdType;
/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType PduR_Init(void);
extern Std_ReturnType PduR_DeInit(void);
extern void PduR_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType PduR_Transmit(PduR_PduIdType PduId, const PduInfoType *PduInfoPtr);
extern Std_ReturnType PduR_CancelTransmit(PduR_PduIdType PduId);
extern void PduR_MainFunction(void);
#ifdef __cplusplus
}
#endif

#endif /* PDUR_H */
