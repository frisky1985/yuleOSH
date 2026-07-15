/**
 * @file Wdg.h
 * @brief Watchdog Driver — Internal watchdog timeout/trigger
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Wdg driver is integrated.
 */

#ifndef WDG_H
#define WDG_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Wdg configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Wdg_ConfigType;

typedef uint8_t Wdg_ModeType;
#define WDGIF_OFF_MODE      0x00U
#define WDGIF_SLOW_MODE     0x01U
#define WDGIF_FAST_MODE     0x02U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Wdg_Init(const Wdg_ConfigType *ConfigPtr);

extern Std_ReturnType Wdg_DeInit(void);

extern void Wdg_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Wdg_SetTriggerCondition(uint16_t TimeoutMs);

extern Std_ReturnType Wdg_SetMode(Wdg_ModeType Mode);

extern Wdg_ModeType Wdg_GetMode(void);

#ifdef __cplusplus
}
#endif

#endif /* WDG_H */
