/**
 * @file Dio.h
 * @brief DIO Driver — Digital I/O channel/port level access
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Dio driver is integrated.
 */

#ifndef DIO_H
#define DIO_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Dio configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Dio_ConfigType;

typedef uint16_t Dio_ChannelType;

typedef uint8_t Dio_LevelType;
#define STD_LOW  0x00U
#define STD_HIGH 0x01U

typedef uint16_t Dio_PortType;

typedef uint32_t Dio_PortLevelType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Dio_Init(const Dio_ConfigType *ConfigPtr);

extern Std_ReturnType Dio_DeInit(void);

extern void Dio_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Dio_LevelType Dio_ReadChannel(Dio_ChannelType ChannelId);

extern Std_ReturnType Dio_WriteChannel(Dio_ChannelType ChannelId, Dio_LevelType Level);

extern Dio_PortLevelType Dio_ReadPort(Dio_PortType PortId);

extern Std_ReturnType Dio_WritePort(Dio_PortType PortId, Dio_PortLevelType Level);

extern Dio_LevelType Dio_FlipChannel(Dio_ChannelType ChannelId);

#ifdef __cplusplus
}
#endif

#endif /* DIO_H */
