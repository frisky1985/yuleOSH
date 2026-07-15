/**
 * @file Eep.h
 * @brief EEPROM Driver — External EEPROM read/write/erase
 *
 * yuleASR MCAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Eep driver is integrated.
 */

#ifndef EEP_H
#define EEP_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Eep configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Eep_ConfigType;

typedef uint32_t Eep_AddressType;

typedef uint32_t Eep_LengthType;

typedef uint8_t Eep_StatusType;
#define EEP_IDLE  0x00U
#define EEP_BUSY  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Eep_Init(const Eep_ConfigType *ConfigPtr);

extern Std_ReturnType Eep_DeInit(void);

extern void Eep_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Eep_Read(Eep_AddressType TargetAddress, uint8_t *TargetDataPtr, Eep_LengthType Length);

extern Std_ReturnType Eep_Write(Eep_AddressType TargetAddress, const uint8_t *SourceDataPtr, Eep_LengthType Length);

extern Std_ReturnType Eep_Erase(Eep_AddressType TargetAddress, Eep_LengthType Length);

extern Eep_StatusType Eep_GetStatus(void);

extern void Eep_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* EEP_H */
