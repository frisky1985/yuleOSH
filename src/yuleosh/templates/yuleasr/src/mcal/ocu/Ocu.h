/**
 * @file Ocu.h
 * @brief OCU Driver — Output Compare
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Ocu driver is integrated.
 */

#ifndef OCU_H
#define OCU_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Ocu configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Ocu_ConfigType;

typedef uint8_t Ocu_ChannelType;

typedef uint32_t Ocu_CompareValueType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Ocu_Init(const Ocu_ConfigType *ConfigPtr);

extern Std_ReturnType Ocu_DeInit(void);

extern void Ocu_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Ocu_EnableOutputCompare(Ocu_ChannelType Channel, Ocu_CompareValueType Value);

extern Std_ReturnType Ocu_DisableOutputCompare(Ocu_ChannelType Channel);

extern Std_ReturnType Ocu_SetCompareValue(Ocu_ChannelType Channel, Ocu_CompareValueType Value);

extern Ocu_CompareValueType Ocu_GetCompareValue(Ocu_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* OCU_H */
