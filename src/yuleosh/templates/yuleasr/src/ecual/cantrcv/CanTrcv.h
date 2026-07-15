/**
 * @file CanTrcv.h
 * @brief CAN Transceiver Driver — External CAN transceiver control
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full CanTrcv driver is integrated.
 */

#ifndef CANTRCV_H
#define CANTRCV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief CanTrcv configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} CanTrcv_ConfigType;

typedef uint8_t CanTrcv_ModeType;
#define CANTRCV_TRCVMODE_NORMAL     0x00U
#define CANTRCV_TRCVMODE_STANDBY    0x01U
#define CANTRCV_TRCVMODE_SLEEP      0x02U

typedef uint8_t CanTrcv_WakeFlagType;
#define CANTRCV_NO_WAKEUP  0x00U
#define CANTRCV_WAKEUP     0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType CanTrcv_Init(const CanTrcv_ConfigType *ConfigPtr);

extern Std_ReturnType CanTrcv_DeInit(void);

extern void CanTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType CanTrcv_SetTrcvMode(uint8_t TrcvIdx, CanTrcv_ModeType Mode);

extern CanTrcv_ModeType CanTrcv_GetTrcvMode(uint8_t TrcvIdx);

extern Std_ReturnType CanTrcv_WakeUp(uint8_t TrcvIdx);

extern CanTrcv_WakeFlagType CanTrcv_CheckWakeFlag(uint8_t TrcvIdx);

extern Std_ReturnType CanTrcv_ClearWakeFlag(uint8_t TrcvIdx);

#ifdef __cplusplus
}
#endif

#endif /* CANTRCV_H */
