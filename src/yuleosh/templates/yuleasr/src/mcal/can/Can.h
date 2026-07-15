/**
 * @file Can.h
 * @brief CAN Driver — CAN 2.0 / CAN FD controller
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Can driver is integrated.
 */

#ifndef CAN_H
#define CAN_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Can configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Can_ConfigType;

typedef uint8_t Can_ControllerType;

typedef uint16_t Can_HwHandleType;

typedef struct { Can_IdType id; uint8_t *sdu; uint8_t sdu_length; Can_PduIdType sw_pdu_handle; } Can_PduType;

typedef uint32_t Can_IdType;

typedef uint16_t Can_PduIdType;

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Can_Init(const Can_ConfigType *ConfigPtr);

extern Std_ReturnType Can_DeInit(void);

extern void Can_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Can_SetBaudrate(Can_ControllerType Controller, uint16_t Baudrate);

extern Std_ReturnType Can_Write(Can_HwHandleType Mailbox, const Can_PduType *PduInfo);

extern Std_ReturnType Can_Read(Can_HwHandleType Mailbox, Can_PduType *PduInfo);

extern void Can_MainFunction_Read(void);

extern void Can_MainFunction_Write(void);

#ifdef __cplusplus
}
#endif

#endif /* CAN_H */
