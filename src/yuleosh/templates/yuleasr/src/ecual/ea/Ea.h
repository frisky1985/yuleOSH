/**
 * @file Ea.h
 * @brief EEPROM Abstraction — NvM backing over external EEPROM
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Ea driver is integrated.
 */

#ifndef EA_H
#define EA_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Ea configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Ea_ConfigType;

typedef uint16_t Ea_BlockIdType;

typedef uint8_t Ea_StatusType;
#define EA_IDLE  0x00U
#define EA_BUSY  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Ea_Init(void);

extern Std_ReturnType Ea_DeInit(void);

extern void Ea_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Ea_Read(Ea_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length);

extern Std_ReturnType Ea_Write(Ea_BlockIdType BlockId, const uint8_t *DataBufferPtr);

extern Ea_StatusType Ea_GetStatus(void);

extern void Ea_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* EA_H */
