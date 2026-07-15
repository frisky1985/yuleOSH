/**
 * @file LinTrcv.h
 * @brief LIN Transceiver Driver — External LIN transceiver control
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full LinTrcv driver is integrated.
 */

#ifndef LINTRCV_H
#define LINTRCV_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief LinTrcv configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} LinTrcv_ConfigType;

typedef uint8_t LinTrcv_ModeType;
#define LINTRCV_TRCVMODE_NORMAL     0x00U
#define LINTRCV_TRCVMODE_STANDBY    0x01U
#define LINTRCV_TRCVMODE_SLEEP      0x02U

typedef uint8_t LinTrcv_WakeFlagType;
#define LINTRCV_NO_WAKEUP  0x00U
#define LINTRCV_WAKEUP     0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType LinTrcv_Init(const LinTrcv_ConfigType *ConfigPtr);

extern Std_ReturnType LinTrcv_DeInit(void);

extern void LinTrcv_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType LinTrcv_SetTrcvMode(uint8_t TrcvIdx, LinTrcv_ModeType Mode);

extern LinTrcv_ModeType LinTrcv_GetTrcvMode(uint8_t TrcvIdx);

extern Std_ReturnType LinTrcv_WakeUp(uint8_t TrcvIdx);

extern LinTrcv_WakeFlagType LinTrcv_CheckWakeFlag(uint8_t TrcvIdx);

#ifdef __cplusplus
}
#endif

#endif /* LINTRCV_H */
