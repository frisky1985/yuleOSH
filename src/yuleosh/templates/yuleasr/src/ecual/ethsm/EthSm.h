/**
 * @file EthSm.h
 * @brief Ethernet State Manager — Controller state arbitration for ETH
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full EthSm driver is integrated.
 */

#ifndef ETHSM_H
#define ETHSM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief EthSm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} EthSm_ConfigType;

typedef uint8_t EthSm_ComModeType;
#define ETHSM_CM_OFF     0x00U
#define ETHSM_CM_COMM    0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType EthSm_Init(void);

extern Std_ReturnType EthSm_DeInit(void);

extern void EthSm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType EthSm_RequestComMode(uint8_t Network, EthSm_ComModeType ComMode);

extern void EthSm_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* ETHSM_H */
