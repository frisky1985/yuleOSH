/**
 * @file Port.h
 * @brief Port Driver — Pin mux/direction/pull configuration
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Port driver is integrated.
 */

#ifndef PORT_H
#define PORT_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Port configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Port_ConfigType;

typedef uint16_t Port_PinType;

typedef uint8_t Port_PinDirectionType;
#define PORT_PIN_IN   0x00U
#define PORT_PIN_OUT  0x01U

typedef uint8_t Port_PinModeType;
#define PORT_PIN_MODE_DIO  0x00U
#define PORT_PIN_MODE_ALT1 0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Port_Init(const Port_ConfigType *ConfigPtr);

extern Std_ReturnType Port_DeInit(void);

extern void Port_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Port_SetPinDirection(Port_PinType Pin, Port_PinDirectionType Direction);

extern Std_ReturnType Port_SetPinMode(Port_PinType Pin, Port_PinModeType Mode);

extern Std_ReturnType Port_RefreshPortDirection(void);

#ifdef __cplusplus
}
#endif

#endif /* PORT_H */
