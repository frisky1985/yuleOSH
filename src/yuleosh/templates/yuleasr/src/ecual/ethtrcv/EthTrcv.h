/**
 * @file EthTrcv.h
 * @brief Ethernet Transceiver Driver — External PHY control
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full EthTrcv driver is integrated.
 */

#ifndef ETHTRCV_H
#define ETHTRCV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief EthTrcv configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} EthTrcv_ConfigType;

typedef uint8_t EthTrcv_ModeType;
#define ETHTRCV_MODE_NORMAL  0x00U
#define ETHTRCV_MODE_SLEEP   0x01U

typedef uint8_t EthTrcv_WakeFlagType;
#define ETHTRCV_NO_WAKEUP  0x00U
#define ETHTRCV_WAKEUP     0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType EthTrcv_Init(const EthTrcv_ConfigType *ConfigPtr);

extern Std_ReturnType EthTrcv_DeInit(void);

extern void EthTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType EthTrcv_SetTrcvMode(uint8_t TrcvIdx, EthTrcv_ModeType Mode);

extern EthTrcv_ModeType EthTrcv_GetTrcvMode(uint8_t TrcvIdx);

extern EthTrcv_WakeFlagType EthTrcv_CheckWakeFlag(uint8_t TrcvIdx);

#ifdef __cplusplus
}
#endif

#endif /* ETHTRCV_H */
