/**
 * @file Mcu.h
 * @brief MCU Driver — Clock/PLL/Reset/Mode management
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Mcu driver is integrated.
 */

#ifndef MCU_H
#define MCU_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Mcu configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Mcu_ConfigType;

typedef uint8_t Mcu_ModeType;
#define MCU_MODE_NORMAL  0x01U
#define MCU_MODE_SLEEP   0x02U
#define MCU_MODE_STOP    0x03U

typedef struct { uint32_t sourceClockHz; uint32_t targetClockHz; } Mcu_ClockType;

typedef uint8_t Mcu_ResetType;
#define MCU_RESET_POWER_ON   0x01U
#define MCU_RESOT_WATCHDOG   0x02U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Mcu_Init(const Mcu_ConfigType *ConfigPtr);

extern Std_ReturnType Mcu_DeInit(void);

extern void Mcu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Mcu_SetMode(Mcu_ModeType Mode);

extern Std_ReturnType Mcu_GetResetReason(Mcu_ResetType *ResetReason);

extern void Mcu_PerformReset(void);

extern Std_ReturnType Mcu_InitClock(const Mcu_ClockType *ClockSetting);

#ifdef __cplusplus
}
#endif

#endif /* MCU_H */
