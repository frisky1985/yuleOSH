/**
 * @file Gpt.h
 * @brief GPT Driver — General-purpose timer channels
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Gpt driver is integrated.
 */

#ifndef GPT_H
#define GPT_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Gpt configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Gpt_ConfigType;

typedef uint8_t Gpt_ChannelType;

typedef uint32_t Gpt_ValueType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Gpt_Init(const Gpt_ConfigType *ConfigPtr);

extern Std_ReturnType Gpt_DeInit(void);

extern void Gpt_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Gpt_StartTimer(Gpt_ChannelType Channel, Gpt_ValueType Value);

extern Std_ReturnType Gpt_StopTimer(Gpt_ChannelType Channel);

extern Gpt_ValueType Gpt_GetTimeElapsed(Gpt_ChannelType Channel);

extern Gpt_ValueType Gpt_GetTimeRemaining(Gpt_ChannelType Channel);

extern Std_ReturnType Gpt_EnableNotification(Gpt_ChannelType Channel);

extern Std_ReturnType Gpt_DisableNotification(Gpt_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* GPT_H */
