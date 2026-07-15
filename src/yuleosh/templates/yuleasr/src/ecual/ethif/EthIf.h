/**
 * @file EthIf.h
 * @brief Ethernet Interface — PDU routing between Eth driver and upper layers
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full EthIf driver is integrated.
 */

#ifndef ETHIF_H
#define ETHIF_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief EthIf configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} EthIf_ConfigType;

typedef uint8_t EthIf_ModeType;
#define ETHIF_MODE_DOWN    0x00U
#define ETHIF_MODE_ACTIVE  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType EthIf_Init(void);

extern Std_ReturnType EthIf_DeInit(void);

extern void EthIf_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType EthIf_SetControllerMode(uint8_t ControllerId, EthIf_ModeType Mode);

extern Std_ReturnType EthIf_Transmit(PduIdType EthIfTxSduId, const PduInfoType *PduInfoPtr);

extern void EthIf_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* ETHIF_H */
