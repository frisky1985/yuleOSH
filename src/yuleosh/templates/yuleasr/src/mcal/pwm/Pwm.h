/**
 * @file Pwm.h
 * @brief PWM Driver — Pulse-width modulation output
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Pwm driver is integrated.
 */

#ifndef PWM_H
#define PWM_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Pwm configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Pwm_ConfigType;

typedef uint8_t Pwm_ChannelType;

typedef uint32_t Pwm_PeriodType;

typedef uint16_t Pwm_DutycycleType;

typedef uint8_t Pwm_ChannelEdgeModeType;
#define PWM_EDGE_CENTER_ALIGNED  0x00U
#define PWM_EDGE_LEFT_ALIGNED    0x01U

typedef uint8_t Pwm_OutputStateType;
#define PWM_LOW  0x00U
#define PWM_HIGH 0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Pwm_Init(const Pwm_ConfigType *ConfigPtr);

extern Std_ReturnType Pwm_DeInit(void);

extern void Pwm_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Pwm_SetPeriodAndDuty(Pwm_ChannelType Channel, Pwm_PeriodType Period, Pwm_ChannelEdgeModeType EdgeMode, Pwm_DutycycleType Dutycycle);

extern Std_ReturnType Pwm_SetDutyCycle(Pwm_ChannelType Channel, Pwm_DutycycleType Dutycycle);

extern Std_ReturnType Pwm_SetOutputToIdle(Pwm_ChannelType Channel);

extern Pwm_OutputStateType Pwm_GetOutputState(Pwm_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* PWM_H */
