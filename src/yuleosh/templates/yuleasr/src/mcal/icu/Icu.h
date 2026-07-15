/**
 * @file Icu.h
 * @brief ICU Driver — Input Capture (period/pulse width/edge)
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Icu driver is integrated.
 */

#ifndef ICU_H
#define ICU_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Icu configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Icu_ConfigType;

typedef uint8_t Icu_ChannelType;

typedef uint32_t Icu_TimeType;

typedef struct { Icu_TimeType activeTime; Icu_TimeType periodTime; } Icu_DutyCycleType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Icu_Init(const Icu_ConfigType *ConfigPtr);

extern Std_ReturnType Icu_DeInit(void);

extern void Icu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Icu_StartSignalMeasurement(Icu_ChannelType Channel);

extern Std_ReturnType Icu_StopSignalMeasurement(Icu_ChannelType Channel);

extern Icu_TimeType Icu_GetTimeElapsed(Icu_ChannelType Channel);

extern Icu_DutyCycleType Icu_GetDutyCycle(Icu_ChannelType Channel);

extern Std_ReturnType Icu_EnableEdgeNotification(Icu_ChannelType Channel);

extern Std_ReturnType Icu_DisableEdgeNotification(Icu_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* ICU_H */
