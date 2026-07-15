/**
 * @file Fee.h
 * @brief Flash EEPROM Emulation (ECUAL-level) — Upper Fee abstraction
 *
 * yuleASR ECUAL stub — skeleton for build integration.
 * Use this as a placeholder until the full Fee driver is integrated.
 */

#ifndef FEE_H
#define FEE_H

#include "Std_Types.h"
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ─── Module-specific types ─────────────────────── */

/** @brief Fee configuration structure (stub) */
typedef struct
{
    uint8_t dummy;  /* Placeholder for generated config */
} Fee_ConfigType;

typedef uint16_t Fee_BlockIdType;

typedef uint8_t Fee_StatusType;
#define FEE_IDLE  0x00U
#define FEE_BUSY  0x01U

/* ─── API declarations ───────────────────────────── */

extern Std_ReturnType Fee_Init(void);

extern Std_ReturnType Fee_DeInit(void);

extern void Fee_GetVersionInfo(Std_VersionInfoType *VersionInfoPtr);

extern Std_ReturnType Fee_Read(Fee_BlockIdType BlockId, uint16_t BlockOffset, uint8_t *DataBufferPtr, uint16_t Length);

extern Std_ReturnType Fee_Write(Fee_BlockIdType BlockId, const uint8_t *DataBufferPtr);

extern Fee_StatusType Fee_GetStatus(void);

extern void Fee_MainFunction(void);

#ifdef __cplusplus
}
#endif

#endif /* FEE_H */
