/**
 * @file Lin.h
 * @brief LIN Driver — LIN 2.2 master/slave
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Lin driver is integrated.
 */

#ifndef LIN_H
#define LIN_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Lin configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Lin_ConfigType;

typedef uint8_t Lin_ChannelType;

typedef struct { uint8_t *sdu; uint8_t length; uint8_t pid; } Lin_PduType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Lin_Init(const Lin_ConfigType *ConfigPtr);

extern Std_ReturnType Lin_DeInit(void);

extern void Lin_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Lin_SendFrame(const Lin_PduType *PduPtr);

extern Std_ReturnType Lin_ReceiveFrame(Lin_PduType *PduPtr);

extern Std_ReturnType Lin_GoToSleep(Lin_ChannelType Channel);

extern Std_ReturnType Lin_GoToSleepInternal(Lin_ChannelType Channel);

extern Std_ReturnType Lin_WakeUp(Lin_ChannelType Channel);

#ifdef __cplusplus
}
#endif

#endif /* LIN_H */
